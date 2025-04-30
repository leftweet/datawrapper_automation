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

# Removed scrape_team_basic_stats function as it's no longer needed

@st.cache_data(ttl=600)
def scrape_play_by_play(original_url, team1_abbr, team2_abbr):
    """
    Scrapes the home and away scores from column 4 of the Play-by-Play table
    starting from the 3rd row, skipping rows where columns 3 and 5 are blank.
    """
    pbp_url = original_url.replace("/boxscores/", "/boxscores/pbp/")
    table_id = 'pbp'

    # Removed st.subheader("Play-by-Play")

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
    embeds the basic iframe in the Streamlit app using components.html,
    and displays the full embed code as a text string.
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
                },
                "publish": {
                    "blocks": {
                        "get-the-data": False
                    }
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
            # Construct the basic iframe HTML using an f-string with white background style
            basic_iframe_html = f"""
<iframe title="{chart_title}" aria-label="Interactive line chart" id="datawrapper-chart-{chart_id}" src="https://datawrapper.dwcdn.net/{chart_id}/1/" scrolling="no" frameborder="0" style="width: 100%; border: none; background-color: white;" height="500" data-external="1"></iframe>
"""
            # Use components.html to embed the iframe
            components.html(basic_iframe_html, height=600)

            st.subheader("Datawrapper Embed Code (Responsive)")
            # Use the exact literal string provided by the user for the responsive embed code
            full_responsive_embed_code = """
<iframe title="Game Flow" aria-label="Interactive line chart" id="datawrapper-chart-kUuOU" src="https://datawrapper.dwcdn.net/kUuOU/1/" scrolling="no" frameborder="0" style="width: 0; min-width: 100% !important; border: none;" height="400" data-external="1"></iframe><script type="text/javascript">!function(){"use strict";window.addEventListener("message",(function(a){if(void 0!==a.data["datawrapper-height"]){var e=document.querySelectorAll("iframe");for(var t in a.data["datawrapper-height"])for(var r,i=0;r=e[i];i++)if(r.contentWindow===a.source){var d=a.data["datawrapper-height"][t]+"px";r.style.height=d}}}))}();
</script>
"""
            # Use st.code to display the string
            st.code(full_responsive_embed_code, language='html')


            # Also display the direct chart URL as text (optional, but can be helpful)
            chart_url = f"https://www.datawrapper.de/_/{chart_id}"
            st.write(f"Direct Chart Link (for reference): {chart_url}")

        else:
            st.warning("Could not create or publish chart, no chart ID available to embed.")
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
    st.title("Game Flow Chart Creator")

    box_score_url = st.text_input("Box Score URL (basketball-reference.com only)", "")

    process_button_pressed = st.button("Process Box Score and Create Chart")


    if process_score_pressed := process_button_pressed:
        if box_score_url:
            st.success(f"Processing URL: {box_score_url}")

            try:
                response = requests.get(box_score_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')

                # --- Game Flow Chart Section ---
                st.header("Game Flow Chart") # Renamed header

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
                else:
                    st.warning("Could not scrape line score to get team abbreviations. Using defaults.")


                # Scrape Play-by-Play data (table will not be displayed)
                pbp_df = scrape_play_by_play(box_score_url, team1_abbr, team2_abbr)
                # Removed st.dataframe(pbp_df) to hide the table

                # --- Trigger Datawrapper Chart Creation ---
                # This is where the datawrapper_api logic is called
                if datawrapper_configured and pbp_df is not None:
                    create_and_publish_datawrapper_chart(pbp_df, team1_abbr, team2_abbr)
                elif datawrapper_configured and pbp_df is None:
                     st.warning("Skipping Datawrapper chart creation because Play-by-Play data could not be scraped.")
                else:
                    st.info("Datawrapper chart creation skipped because API is not configured.")

                # Removed the display of the line score table
                # Removed the sections for Top Scorers and Player of the Game

            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching the URL: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred during scraping or processing: {e}")

        else:
            st.error("Please enter a valid Box Score URL.")


if __name__ == "__main__":
    main()
