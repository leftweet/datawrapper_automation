import streamlit as st
import requests
from bs4 import BeautifulSoup
from bs4.element import Comment # Import Comment
import pandas as pd

# (Keep find_element_in_soup, scrape_line_score, and scrape_team_basic_stats functions as they are)
def find_element_in_soup(soup, element_type, element_id):
    """
    Finds an element by its type and ID within a BeautifulSoup object,
    checking both direct presence and commented-out sections.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the page.
        element_type (str): The type of element to find (e.g., 'table', 'div').
        element_id (str): The ID of the element to find.

    Returns:
        BeautifulSoup tag or None: The element if found, otherwise None.
    """
    # Try to find the element directly
    element = soup.find(element_type, id=element_id)

    # If not found directly, search within commented-out sections
    if not element:
         comments = soup.find_all(string=lambda text: isinstance(text, Comment))
         for comment in comments:
             comment_soup = BeautifulSoup(comment, 'html.parser')
             element = comment_soup.find(element_type, id=element_id)
             if element:
                 break # Found the element in a comment

    return element


def scrape_line_score(soup):
    """
    Scrapes the line score table from a BeautifulSoup object.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the page.

    Returns:
        pandas.DataFrame or None: A DataFrame containing the line score data,
                                  or None if the table is not found or parsing fails.
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

    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the page.
        team_abbr (str): The abbreviation of the team (e.g., 'CLE', 'MIA').

    Returns:
        pandas.DataFrame or None: A DataFrame containing the team's basic stats,
                                  or None if the div/table is not found or parsing fails.
    """
    div_id = f'div_box-{team_abbr}-game-basic' # ID of the container div
    table_id = f'box-{team_abbr}-game-basic' # ID of the table inside the div

    container_div = find_element_in_soup(soup, 'div', div_id)

    if not container_div:
        st.warning(f"Could not find the '{div_id}' container div on the page for {team_abbr}.")
        return None

    team_stats_table = container_div.find('table', id=table_id)

    if not team_stats_table:
        st.warning(f"Could not find the '{table_id}' table inside the '{div_id}' div for {team_abbr}.")
        return None


    try:
        # Extract table headers
        headers = []
        header_row_element = None

        thead = team_stats_table.find('thead')
        if thead:
             header_rows = thead.find_all('tr')
             # Iterate through header rows to find the one with main stats headers (e.g., 'MP')
             for row in header_rows:
                 row_cells = row.find_all(['th', 'td'])
                 cell_texts = [cell.get_text().strip() for cell in row_cells]
                 if 'MP' in cell_texts:
                     headers = cell_texts
                     header_row_element = row
                     break # Found the header row

        if not header_row_element:
             st.warning(f"Could not identify a suitable header row in the thead for {team_abbr}.")
             return None


        # Extract table rows (player stats)
        data = []
        if team_stats_table.find('tbody'): # Ensure tbody exists
             # Select only tbody rows that are not total rows ('thead' class) or empty rows
             player_rows = team_stats_table.select('tbody tr:not(.thead)')

             for row in player_rows:
                row_cells = row.find_all(['th', 'td'])
                # Skip empty rows or rows that don't look like player data (e.g., subheaders like 'Starters')
                # Check if the first cell contains player name-like content
                if not row_cells or row_cells[0].get_text().strip() == '' or row_cells[0].name != 'th':
                     continue # Skip if empty or not a player header cell (usually 'th' for name)


                row_data = [cell.get_text().strip() for cell in row_cells]
                data.append(row_data)

        if data: # Check if data was extracted
             max_cols = len(headers)
             # Check consistency of row lengths before padding
             inconsistent_rows = [i for i, row in enumerate(data) if len(row) != max_cols]
             # Removed the warning about inconsistent rows before padding

             padded_data = [row + [None] * (max_cols - len(row)) for row in data]
             df = pd.DataFrame(padded_data, columns=headers)
             return df
        else:
            st.warning(f"No data rows extracted from the '{table_id}' table inside '{div_id}' for {team_abbr}.")
            return None

    except Exception as e: # Catch errors during header/data parsing
        st.error(f"An error occurred while parsing the table content for '{table_id}' inside '{div_id}' for {team_abbr}: {e}")
        return None


# The main function is updated to simplify the Top Scorers headers
def main():
    """
    Streamlit app for analyzing box scores.
    """
    st.title("Box Score Analyzer")

    st.write("Enter the URL of a basketball-reference.com box score to analyze:")

    # Input field for the box score URL
    box_score_url = st.text_input("Box Score URL", "")

    # Button to trigger processing
    process_button_pressed = st.button("Process Box Score")

    # Optional: Add some explanatory text initially
    if not process_button_pressed:
         st.info("Enter a URL and click 'Process Box Score' to see the analysis sections.")

    # This block executes only when the button is pressed
    if process_score_pressed := process_button_pressed:
        if box_score_url:
            st.success(f"Processing URL: {box_score_url}")

            # Fetch the page content once
            try:
                response = requests.get(box_score_url)
                response.raise_for_status() # Raise an exception for bad status codes
                soup = BeautifulSoup(response.content, 'html.parser')

                # --- Team Trends Section ---
                st.header("Team Trends")

                # Scrape and display the line score table
                st.subheader("Line Score")
                line_score_df = scrape_line_score(soup)

                # Variables to hold team stats dataframes and abbreviations
                team1_stats_df = None
                team2_stats_df = None
                team1_abbr = None
                team2_abbr = None


                if line_score_df is not None:
                    st.dataframe(line_score_df)

                    if len(line_score_df) >= 2:
                        try:
                            # Team abbr is in the first column (index 0)
                            team1_abbr = line_score_df.iloc[0, 0]
                            team2_abbr = line_score_df.iloc[1, 0]

                            # Scrape and display stats for Team 1
                            st.subheader(f"{team1_abbr} Basic Stats")
                            team1_stats_df = scrape_team_basic_stats(soup, team1_abbr)
                            if team1_stats_df is not None:
                                st.dataframe(team1_stats_df)


                            # Scrape and display stats for Team 2
                            st.subheader(f"{team2_abbr} Basic Stats")
                            team2_stats_df = scrape_team_basic_stats(soup, team2_abbr)
                            if team2_stats_df is not None:
                                st.dataframe(team2_stats_df)

                        except IndexError:
                             st.error("Could not extract team abbreviations from the line score table.")
                        except Exception as e:
                             st.error(f"An error occurred while processing team abbreviations: {e}")


                    else:
                        st.warning("Line score does not contain data for two teams to scrape individual stats.")

                else:
                    st.warning("Could not display line score. Cannot proceed to scrape team stats.")


                # --- Top Scorers Section ---
                st.header("Top Scorers") # Changed header text

                all_player_stats = []

                # Process Team 1 stats
                if team1_stats_df is not None and team1_abbr:
                    if 'Starters' in team1_stats_df.columns and 'PTS' in team1_stats_df.columns:
                        team1_players = team1_stats_df[['Starters', 'PTS']].copy()
                        team1_players = team1_players.rename(columns={'Starters': 'Player'})
                        team1_players['Team'] = team1_abbr
                        all_player_stats.append(team1_players)
                    else:
                        st.warning(f"Could not find 'Starters' or 'PTS' columns in {team1_abbr} stats.")


                # Process Team 2 stats
                if team2_stats_df is not None and team2_abbr:
                    if 'Starters' in team2_stats_df.columns and 'PTS' in team2_stats_df.columns:
                        team2_players = team2_stats_df[['Starters', 'PTS']].copy()
                        team2_players = team2_players.rename(columns={'Starters': 'Player'})
                        team2_players['Team'] = team2_abbr
                        all_player_stats.append(team2_players)
                    else:
                         st.warning(f"Could not find 'Starters' or 'PTS' columns in {team2_abbr} stats.")

                # Combine and sort stats if data was collected
                if all_player_stats:
                    combined_df = pd.concat(all_player_stats, ignore_index=True)

                    # Convert 'PTS' to numeric, handling errors
                    combined_df['PTS'] = pd.to_numeric(combined_df['PTS'], errors='coerce').fillna(0)

                    # Sort by PTS descending
                    sorted_players_df = combined_df.sort_values(by='PTS', ascending=False)

                    # --- Filter for Top 5 with ties ---
                    if len(sorted_players_df) > 0:
                        if len(sorted_players_df) >= 5:
                            fifth_player_pts = sorted_players_df.iloc[4]['PTS']
                            top_scorers_df = sorted_players_df[sorted_players_df['PTS'] >= fifth_player_pts]
                        else:
                            top_scorers_df = sorted_players_df

                        # Removed: st.subheader("Top Scorers (including ties with 5th place)")
                        st.dataframe(top_scorers_df)
                    else:
                        st.info("No player stats available to determine top scorers.")

                else:
                    st.info("Player stats could not be processed for Top Scorers.")


                # --- Player of the Game Section ---
                st.header("Player of the Game")
                st.write("Section to highlight the Player of the Game.")
                st.warning("Logic for determining Player of the Game is not yet implemented.")


            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching the URL: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

        else:
            st.error("Please enter a valid Box Score URL.")


if __name__ == "__main__":
    main()
