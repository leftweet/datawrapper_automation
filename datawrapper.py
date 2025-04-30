# -*- coding: utf-8 -*-
"""datawrapper.py - Streamlit app with Datawrapper integration"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
from bs4.element import Comment
import pandas as pd
import json
import os
import csv
import streamlit.components.v1 as components # Import components for embedding HTML
# Removed time import as retry logic is removed

# --- Datawrapper API Configuration ---
# Use Streamlit secrets for the API token
# Instructions: Create a .streamlit/secrets.toml file in your app's directory
# Add the following line: DATAWRAPPER_API_TOKEN = "YOUR_API_TOKEN_HERE"
try:
    API_TOKEN = st.secrets["DATAWRAPPER_API_TOKEN"]
    BASE_URL = 'https://api.datawrapper.de/v3'
    HEADERS_JSON = {
        'Authorization': f'Bearer {API_TOKEN}',
        'Content-Type': 'application/json'
    }
    HEADERS_CSV = {
        'Authorization': f'Bearer {API_TOKEN}',
        'Content-Type': 'text/csv'
    }
    datawrapper_configured = True
except KeyError:
    st.warning("Datawrapper API token not found in Streamlit secrets. Datawrapper functionality will be disabled.")
    datawrapper_configured = False
except Exception as e:
    st.error(f"Error configuring Datawrapper API: {e}")
    datawrapper_configured = False

# --- Helper Functions ---
def find_element_in_soup(soup, element_type, element_id):
    """
    Finds an element by its type and ID within a BeautifulSoup object,
    checking both direct presence and commented-out sections.
    """
    element = soup.find(element_type, id=element_id)
    if not element:
         comments = soup.find_all(string=lambda text: isinstance(text, Comment))
         for comment in comments:
             comment_soup = BeautifulSoup(comment, 'html.parser')
             element = comment_soup.find(element_type, id=element_id)
             if element:
                 break
    return element

def scrape_line_score(soup):
    """
    Scrapes the line score table from a BeautifulSoup object.
    """
    table_id = 'line_score'
    line_score_table = find_element_in_soup(soup, 'table', table_id)
    if line_score_table:
        try:
            headers = []
            header_row = line_score_table.select_one('thead tr:nth-of-type(2)')
            if header_row:
                 headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
                 headers = [h if h != '\xa0' else 'Team' for h in headers]
            data = []
            for row in line_score_table.select('tbody tr'):
                row_data = [cell.get_text().strip() for cell in row.find_all(['th', 'td'])]
                data.append(row_data)
            if headers and data:
                df = pd.DataFrame(data, columns=headers)
                return df
            else:
                return None
        except Exception as e:
            st.error(f"Error parsing '{table_id}' table: {e}")
            return None
    else:
        return None

def scrape_team_basic_stats(soup, team_abbr):
    """
    Scrapes the basic box score stats table for a specific team by finding its container div.
    """
    div_id = f'div_box-{team_abbr}-game-basic'
    table_id = f'box-{team_abbr}-game-basic'
    container_div = find_element_in_soup(soup, 'div', div_id)
    if not container_div:
        st.warning(f"Could not find the '{div_id}' container div on the page for {team_abbr}.")
        return None
    team_stats_table = container_div.find('table', id=table_id)
    if not team_stats_table:
        st.warning(f"Could not find the '{table_id}' table inside the '{div_id}' div for {team_abbr}.")
        return None
    try:
        headers = []
        header_row_element = None
        thead = team_stats_table.find('thead')
        if thead:
             header_rows = thead.find_all('tr')
             for row in header_rows:
                 row_cells = row.find_all(['th', 'td'])
                 cell_texts = [cell.get_text().strip() for cell in row_cells]
                 if 'MP' in cell_texts:
                     headers = cell_texts
                     header_row_element = row
                     break
        if not header_row_element:
             st.warning(f"Could not identify a suitable header row in the thead for {team_abbr}.")
             return None
        data = []
        if team_stats_table.find('tbody'):
             player_rows = team_stats_table.select('tbody tr:not(.thead)')
             for row in player_rows:
                row_cells = row.find_all(['th', 'td'])
                if not row_cells or row_cells[0].get_text().strip() == '' or row_cells[0].name != 'th':
                     continue
                row_data = [cell.get_text().strip() for cell in row_cells]
                data.append(row_data)
        if data:
             max_cols = len(headers)
             padded_data = [row + [None] * (max_cols - len(row)) for row in data]
             df = pd.DataFrame(padded_data, columns=headers)
             return df
        else:
            st.warning(f"No data rows extracted from the '{table_id}' table inside '{div_id}' for {team_abbr}.")
            return None
    except Exception as e:
        st.error(f"An error occurred while parsing the table content for '{table_id}' inside '{div_id}' for {team_abbr}: {e}")
        return None

@st.cache_data(ttl=600)
def scrape_play_by_play(original_url, team1_abbr, team2_abbr):
    """
    Scrapes the home and away scores from column 4 of the Play-by-Play table
    starting from the 3rd row, skipping rows where columns 3 and 5 are blank.
    """
    pbp_url = original_url.replace("/boxscores/", "/boxscores/pbp/")
    table_id = 'pbp'

    st.subheader("Play-by-Play")

    try:
        response = requests.get(pbp_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        pbp_table = find_element_in_soup(soup, 'table', table_id)

        if pbp_table:
            all_trs = pbp_table.find_all('tr')
            data = []
            # Headers will only be the team abbreviations now
            output_headers = [team1_abbr, team2_abbr]

            if len(all_trs) >= 3:
                for row in all_trs[2:]:
                    row_cells = row.find_all(['th', 'td'])

                    # Need at least 5 cells to check columns 3 (idx 2) and 5 (idx 4) and extract column 4 (idx 3)
                    # We no longer need cell 1 (idx 0) for Time in the output data
                    if len(row_cells) >= 5:
                        # time_text = row_cells[0].get_text().strip() if len(row_cells) > 0 and row_cells[0] else "" # Removed time_text
                        col3_text = row_cells[2].get_text().strip() if len(row_cells) > 2 and row_cells[2] else ""
                        score_text = row_cells[3].get_text().strip() if len(row_cells) > 3 and row_cells[3] else ""
                        col5_text = row_cells[4].get_text().strip() if len(row_cells) > 4 and row_cells[4] else ""

                        if col3_text == "" and col5_text == "":
                             continue

                        home_score_str = "N/A"
                        away_score_str = "N/A"

                        if score_text and '-' in score_text:
                            scores = score_text.split('-')
                            if len(scores) == 2:
                                home_score_str = scores[0].strip()
                                away_score_str = scores[1].strip()

                        # Append a list with home score and away score (Time is removed)
                        data.append([home_score_str, away_score_str])

                if data:
                    df = pd.DataFrame(data, columns=output_headers)
                    # Convert score columns to numeric, coercing errors
                    df[team1_abbr] = pd.to_numeric(df[team1_abbr], errors='coerce').fillna(0)
                    df[team2_abbr] = pd.to_numeric(df[team2_abbr], errors='coerce').fillna(0)
                    # The DataFrame index (0, 1, 2, ...) will serve as the x-axis
                    return df
                else:
                    st.warning(f"No score data extracted from the PBP table starting from the 3rd row (after skipping rows where columns 3 and 5 were both blank or score format was invalid).")
                    return None
            else:
                st.warning(f"PBP table has fewer than 3 'tr' rows ({len(all_trs)}). Cannot start extraction from the 3rd row.")
                return None
        else:
            st.warning(f"Could not find the '{table_id}' table on the PBP page.")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching the PBP URL: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during PBP scraping: {e}")
        return None

# --- Datawrapper API Interaction Function ---
def create_and_publish_datawrapper_chart(df, team1_abbr, team2_abbr):
    """
    Creates a Datawrapper chart from a pandas DataFrame, publishes it,
    and embeds the basic iframe in the Streamlit app using components.html.
    """
    if not datawrapper_configured:
        st.warning("Datawrapper API is not configured. Skipping chart creation.")
        return

    # Removed the "Datawrapper Chart Creation" header and step-by-step messages

    # Define temporary CSV filename
    csv_filename = f"pbp_data_{team1_abbr}_{team2_abbr}.csv"
    chart_url = None # Initialize chart_url
    chart_id = None # Initialize chart_id

    try:
        # Save DataFrame to temporary CSV (index=True to include the numerical index)
        df.to_csv(csv_filename, index=True) # Save index as the first column

        # Read column headers from the saved CSV (including the new index header)
        with open(csv_filename, newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=',')
            headers = next(reader)

        # The headers will now include an empty string or 'None' for the index column,
        # followed by the two team abbreviations. We need at least 3 columns total.
        if len(headers) < 3:
             st.error("CSV must have at least 3 columns (Index, Team1_Score, Team2_Score).")
             return

        # The actual data columns start from the second column (index 1)
        team_a_col = headers[1] # Should be team1_abbr
        team_b_col = headers[2] # Should be team2_abbr
        chart_title = f"{team_a_col} vs. {team_b_col} Game Flow" # Get chart title from team abbreviations

        # Step 2: Create the chart
        chart_config = {
            "title": chart_title, # Use the dynamically created title
            "type": "d3-lines"
        }
        response = requests.post(f"{BASE_URL}/charts", headers=HEADERS_JSON, data=json.dumps(chart_config))
        response.raise_for_status()
        chart_id = response.json()['id']

        # Step 3: Upload CSV data
        upload_url = f"{BASE_URL}/charts/{chart_id}/data"
        with open(csv_filename, 'r', encoding='utf-8') as file:
            csv_data = file.read()
        upload_response = requests.put(upload_url, headers=HEADERS_CSV, data=csv_data.encode('utf-8'))
        upload_response.raise_for_status()

        # Step 4: Construct dynamic metadata
        metadata_url = f"{BASE_URL}/charts/{chart_id}"
        metadata_patch = {
            "metadata": {
                "describe": {
                    "source-name": "Basketball Reference Play-by-Play",
                    "source-url": "", # Consider adding the original_url here if possible
                    "intro": f"Game flow chart for {team_a_col} vs. {team_b_col}.",
                    "byline": "",
                    "aria-description": f"Line chart showing the score progression for {team_a_col} and {team_b_col} throughout the game.",
                    "number-format": "-",
                    "number-divisor": 0,
                    "number-append": "",
                    "number-prepend": ""
                },
                "visualize": {
                    "dark-mode-invert": True,
                    "lines": {
                        team_a_col: {
                            "symbols": {"on": "last", "style": "hollow", "enabled": True},
                            "valueLabels": {"first": False, "enabled": True}
                        },
                        team_b_col: {
                            "symbols": {"on": "last", "style": "hollow", "enabled": True},
                            "enabled": True,
                            "valueLabels": {"first": False, "enabled": True}
                        }
                    },
                     "legend": {
                         "enabled": True,
                         "position": "top",
                         "alignment": "left"
                     },
                    "highlighted-series": [],
                    "highlighted-values": [],
                    "sharing": {"enabled": False, "url": "", "auto": False},
                    "shape": "fixed",
                    "size": "fixed",
                    "x-pos": "off", # Let Datawrapper handle x-axis from index
                    "y-pos": "left",
                    "x-axis": {"log": False, "range": ["", ""], "ticks": []}, # Let Datawrapper handle x-axis ticks
                    "x-grid": "off",
                    "y-axis": {"log": False, "range": ["", ""], "ticks": []},
                    "y-grid": "on",
                    "compare": {"enabled": False, "differenceLabel": True},
                    "opacity": 1,
                    "scale-y": "linear",
                    "sort-by": "first",
                    "tooltip": {"body": "", "title": "", "sticky": False, "enabled": True},
                    "category": "direct", # 'direct' is suitable when the first column is the x-axis
                    "max-size": 10,
                    "outlines": False,
                    "overlays": [],
                    "x-format": "auto", # Let Datawrapper handle x-axis format
                    "y-format": "auto",
                    "x-grid-format": ".",
                    "color-key": True,
                    "base-color": "#2e2e2e",
                    "fixed-size": 5,
                    "grid-lines": "show",
                    "regression": False,
                    "sort-areas": "keep",
                    "auto-labels": True,
                    "bar-padding": 60,
                    "label-space": 30,
                    "sort-values": False,
                    "stack-areas": True,
                    "valueLabels": {
                        "show": "hover",
                        "enabled": True,
                        "placement": "outside"
                    },
                    "yAxisLabels": {
                        "enabled": True,
                        "alignment": "left",
                        "placement": "outside"
                    },
                    "area-opacity": 0.5,
                    "custom-area-fills": [
                        {
                            "id": "area_fill_1",
                            "to": team_b_col,
                            "from": team_a_col,
                            "color": "#cccccc",
                            "opacity": 0.3,
                            "colorNegative": "#E31A1C",
                            "interpolation": "linear",
                            "useMixedColors": False
                        }
                    ],
                    "custom-range-y": [
                        "-2",
                        ""
                    ],
                    "connector-lines": True,
                    "interpolation": "monotone-x",
                    "hover-highlight": True,
                    "plotHeightFixed": 350,
                    "show-color-key": True,
                }
            }
        }
        patch_response = requests.patch(metadata_url, headers=HEADERS_JSON, data=json.dumps(metadata_patch))
        patch_response.raise_for_status()

        # Step 5: Publish chart
        publish_url = f"{BASE_URL}/charts/{chart_id}/publish"
        publish_response = requests.post(publish_url, headers={'Authorization': f'Bearer {API_TOKEN}'})
        publish_response.raise_for_status()

        # --- Embed the basic iframe using components.html with white background ---
        if chart_id:
            st.subheader("Datawrapper Game Flow Chart")
            # Construct the basic iframe HTML using an f-string with white background style
            basic_iframe_html = f"""
<iframe title="{chart_title}" aria-label="Interactive line chart" id="datawrapper-chart-{chart_id}" src="https://datawrapper.dwcdn.net/{chart_id}/1/" scrolling="no" frameborder="0" style="width: 100%; border: none; background-color: white;" height="500" data-external="1"></iframe>
"""
            # Use components.html to embed the iframe
            components.html(basic_iframe_html, height=600)

            # Also display the direct chart URL as text
            chart_url = f"https://www.datawrapper.de/_/{chart_id}"
            st.write(f"Direct Chart Link (for reference): {chart_url}")

        else:
            st.warning("Could not create or publish chart, no chart ID available to embed.")
            # Fallback to showing the link if embedding fails (though chart_id should be available here if publish succeeded)
            # This else block is primarily for safety if chart_id wasn't set for some unexpected reason
            st.subheader("Datawrapper Chart Link")
            st.write("Chart ID not available. Could not generate link.")


    except requests.exceptions.RequestException as e:
        st.error(f"Datawrapper API Error: {e}")
        if e.response is not None:
            st.error(f"Error Response Status Code: {e.response.status_code}")
            st.error(f"Error Response Body: {e.response.text}")
    except FileNotFoundError:
        st.error(f"Temporary CSV file not found: {csv_filename}")
    except Exception as e:
        st.error(f"An unexpected error occurred during Datawrapper interaction: {e}")
    finally:
        # Clean up the temporary CSV file
        if os.path.exists(csv_filename):
            os.remove(csv_filename)


# --- Main Streamlit App Logic ---
def main():
    """
    Streamlit app for analyzing box scores and creating Datawrapper charts.
    """
    st.title("Box Score Analyzer & Datawrapper Chart Creator")

    st.write("Enter the URL of a basketball-reference.com box score to analyze:")

    box_score_url = st.text_input("Box Score URL", "")

    process_button_pressed = st.button("Process Box Score and Create Chart")

    if not process_button_pressed:
         st.info("Enter a URL and click 'Process Box Score and Create Chart' to see the analysis and generate a Datawrapper chart.")
         st.info("Make sure your Datawrapper API token is configured in `.streamlit/secrets.toml`.")


    if process_score_pressed := process_button_pressed:
        if box_score_url:
            st.success(f"Processing URL: {box_score_url}")

            try:
                response = requests.get(box_score_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')

                # --- Team Trends Section ---
                st.header("Team Trends")

                line_score_df = scrape_line_score(soup)

                team1_abbr = "Team1"
                team2_abbr = "Team2"

                if line_score_df is not None and len(line_score_df) >= 2:
                     try:
                          team1_abbr = line_score_df.iloc[0, 0]
                          team2_abbr = line_score_df.iloc[1, 0]
                     except IndexError:
                          st.warning("Could not extract team abbreviations from the line score table for PBP headers. Using defaults.")
                     except Exception as e:
                          st.warning(f"An error occurred while extracting team abbreviations: {e}")

                # Scrape and display the Play-by-Play table
                pbp_df = scrape_play_by_play(box_score_url, team1_abbr, team2_abbr)
                if pbp_df is not None:
                    st.dataframe(pbp_df)

                    # --- Trigger Datawrapper Chart Creation ---
                    # This is where the datawrapper_api logic is called
                    if datawrapper_configured:
                        create_and_publish_datawrapper_chart(pbp_df, team1_abbr, team2_abbr)
                    else:
                        st.info("Datawrapper chart creation skipped because API is not configured.")

                # Display the line score table
                st.subheader("Line Score")
                team1_stats_df = None
                team2_stats_df = None

                if line_score_df is not None:
                    st.dataframe(line_score_df)
                    if len(line_score_df) >= 2:
                        try:
                            st.subheader(f"{team1_abbr} Basic Stats")
                            team1_stats_df = scrape_team_basic_stats(soup, team1_abbr)
                            if team1_stats_df is not None:
                                st.dataframe(team1_stats_df)

                            st.subheader(f"{team2_abbr} Basic Stats")
                            team2_stats_df = scrape_team_basic_stats(soup, team2_abbr)
                            if team2_stats_df is not None:
                                st.dataframe(team2_stats_df)
                        except Exception as e:
                             st.error(f"An error occurred while processing team stats sections: {e}")
                    else:
                        st.warning("Line score does not contain data for two teams to scrape individual stats.")
                else:
                    st.warning("Could not display line score. Cannot proceed to scrape team stats.")

                # --- Top Scorers Section ---
                st.header("Top Scorers")
                all_player_stats = []
                required_cols_top_scorers = ['Starters', 'PTS']

                if team1_stats_df is not None and team1_abbr:
                    if all(col in team1_stats_df.columns for col in required_cols_top_scorers):
                        team1_players_top_scorers = team1_stats_df[required_cols_top_scorers].copy()
                        team1_players_top_scorers = team1_players_top_scorers.rename(columns={'Starters': 'Player'})
                        team1_players_top_scorers['Team'] = team1_abbr
                        all_player_stats.append(team1_players_top_scorers)
                    else:
                        st.warning(f"Missing required columns for Top Scorers in {team1_abbr} stats.")

                if team2_stats_df is not None and team2_abbr:
                    if all(col in team2_stats_df.columns for col in required_cols_top_scorers):
                        team2_players_top_scorers = team2_stats_df[required_cols_top_scorers].copy()
                        team2_players_top_scorers = team2_players_top_scorers.rename(columns={'Starters': 'Player'})
                        team2_players_top_scorers['Team'] = team2_abbr
                        all_player_stats.append(team2_players_top_scorers)
                    else:
                         st.warning(f"Missing required columns for Player of the Game in {team2_abbr} stats.")

                if all_player_stats:
                    combined_df_top_scorers = pd.concat(all_player_stats, ignore_index=True)
                    combined_df_top_scorers['PTS'] = pd.to_numeric(combined_df_top_scorers['PTS'], errors='coerce').fillna(0)
                    sorted_players_df_top_scorers = combined_df_top_scorers.sort_values(by='PTS', ascending=False)

                    if len(sorted_players_top_scorers) > 0:
                        if len(sorted_players_top_scorers) >= 5:
                            fifth_player_pts = sorted_players_top_scorers.iloc[4]['PTS']
                            top_scorers_df = sorted_players_top_scorers[sorted_players_top_scorers['PTS'] >= fifth_player_pts]
                        else:
                            top_scorers_df = sorted_players_top_scorers
                        st.dataframe(top_scorers_df)
                    else:
                        st.info("No player stats available to determine top scorers.")
                else:
                    st.info("Player stats could not be processed for Top Scorers.")

                # --- Player of the Game Section ---
                st.header("Player of the Game")
                pog_candidates_list = []
                required_cols_pog = ['Starters', 'GmSc', 'TRB', 'AST', 'STL', 'BLK', 'PTS']

                if team1_stats_df is not None and team1_abbr:
                    if all(col in team1_stats_df.columns for col in required_cols_pog):
                        team1_players_pog = team1_stats_df[required_cols_pog].copy()
                        team1_players_pog = team1_players_pog.rename(columns={'Starters': 'Player'})
                        pog_candidates_list.append(team1_players_pog)
                    else:
                         st.warning(f"Missing required columns for Player of the Game in {team1_abbr} stats.")

                if team2_stats_df is not None and team2_abbr:
                    if all(col in team2_stats_df.columns for col in required_cols_pog):
                        team2_players_pog = team2_stats_df[required_cols_pog].copy()
                        team2_players_pog = team2_players_top_scorers.rename(columns={'Starters': 'Player'})
                        pog_candidates_list.append(team2_players_pog)
                    else:
                         st.warning(f"Missing required columns for Player of the Game in {team2_abbr} stats.")

                if pog_candidates_list:
                    combined_pog_candidates_df = pd.concat(pog_candidates_list, ignore_index=True)
                    combined_pog_candidates_df['GmSc'] = pd.to_numeric(combined_pog_candidates_df['GmSc'], errors='coerce').fillna(0)

                    if len(combined_pog_candidates_df) > 0:
                        player_of_the_game_index = combined_pog_candidates_df['GmSc'].idxmax()
                        player_of_the_game_row = combined_pog_candidates_df.loc[player_of_the_game_index]
                        pog_display_cols = ['Player', 'TRB', 'AST', 'STL', 'BLK', 'PTS', 'GmSc']
                        player_of_the_game_stats = player_of_the_game_row[pog_display_cols]
                        player_of_the_game_df = player_of_the_game_stats.to_frame().T
                        st.dataframe(player_of_the_game_df)
                    else:
                        st.info("No player stats available to determine Player of the Game.")
                else:
                    st.info("Player stats could not be processed for Player of the Game.")

            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching the URL: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred during scraping or processing: {e}")

        else:
            st.error("Please enter a valid Box Score URL.")


if __name__ == "__main__":
    main()
