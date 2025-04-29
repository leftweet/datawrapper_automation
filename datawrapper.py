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

# (Keep scrape_line_score function as is)
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

# (Keep scrape_team_basic_stats function as is)
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
             # Select only tbody rows that are not total rows ('thead' class)
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

# Updated function to scrape the score margin from column 4 of the PBP table,
# starting from the 3rd row and skipping rows where columns 3 and 5 are blank.
@st.cache_data(ttl=600) # Add caching decorator (cache for 10 minutes)
def scrape_play_by_play(original_url):
    """
    Scrapes the score margin from column 4 of the Play-by-Play table starting from the 3rd row,
    skipping rows where columns 3 and 5 are blank.

    Args:
        original_url (str): The original box score URL.

    Returns:
        pandas.DataFrame or None: A DataFrame containing the score margin data,
                                  or None if scraping fails or the table is not found.
    """
    # Construct the PBP URL
    pbp_url = original_url.replace("/boxscores/", "/boxscores/pbp/")
    table_id = 'pbp' # ID of the Play-by-Play table

    st.subheader("Play-by-Play")

    try:
        # Fetch the PBP page content
        response = requests.get(pbp_url)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the PBP table by its ID, handling comments
        pbp_table = find_element_in_soup(soup, 'table', table_id)

        if pbp_table:
            # Find all rows directly within the table
            all_trs = pbp_table.find_all('tr')

            data = []

            # Start iterating from the 3rd row (index 2)
            # Ensure there are at least 3 rows to start from the 3rd
            if len(all_trs) >= 3:
                # Slice from index 2 to the end to get rows 3 onwards
                for row in all_trs[2:]:
                    row_cells = row.find_all(['th', 'td'])

                    # Need at least 5 cells to check columns 3 (idx 2) and 5 (idx 4) and extract column 4 (idx 3)
                    if len(row_cells) >= 5:
                        # Safely get cell text for columns 3, 4, and 5
                        col3_text = row_cells[2].get_text().strip() if len(row_cells) > 2 and row_cells[2] else ""
                        score_text = row_cells[3].get_text().strip() if len(row_cells) > 3 and row_cells[3] else ""
                        col5_text = row_cells[4].get_text().strip() if len(row_cells) > 4 and row_cells[4] else ""

                        # Skip row if column 3 AND column 5 are both blank
                        if col3_text == "" and col5_text == "":
                             continue # Skip this row

                        # Process the score text to calculate the margin
                        margin = "N/A" # Default value if score format is unexpected
                        if score_text and '-' in score_text:
                            scores = score_text.split('-')
                            if len(scores) == 2 and scores[0].isdigit() and scores[1].isdigit():
                                try:
                                    home_score = int(scores[0])
                                    away_score = int(scores[1])
                                    margin = home_score - away_score
                                except ValueError:
                                    # Should not happen if isdigit() is true, but as a safeguard
                                    pass


                        data.append([margin]) # Append a list with only the calculated margin


                if data: # Check if data was extracted
                    # No headers needed, pandas will assign default columns (0)
                    df = pd.DataFrame(data)
                    st.success("PBP data processing complete.")
                    return df
                else:
                    st.warning(f"No score margin data extracted from the PBP table starting from the 3rd row (after skipping rows where columns 3 and 5 were both blank or score format was invalid).")
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
    except Exception as e: # Catch unexpected errors during the scraping process
        st.error(f"An unexpected error occurred during PBP scraping: {e}")
        return None


# The main function remains the same in how it calls scrape_play_by_play
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

            # Fetch the page content once for box score data (needed for line score and basic stats)
            try:
                response = requests.get(box_score_url)
                response.raise_for_status() # Raise an exception for bad status codes
                soup = BeautifulSoup(response.content, 'html.parser')

                # --- Team Trends Section ---
                st.header("Team Trends")

                # Scrape and display the Play-by-Play table FIRST
                # PBP scraping fetches its own URL
                pbp_df = scrape_play_by_play(box_score_url)
                if pbp_df is not None:
                    st.dataframe(pbp_df)
                # Warning is displayed inside scrape_play_by_play if it fails


                # Scrape and display the line score table (using the initially fetched soup)
                st.subheader("Line Score")
                line_score_df = scrape_line_score(soup) # Pass the initial soup

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

                            # Scrape and display stats for Team 1 (using the initial soup)
                            st.subheader(f"{team1_abbr} Basic Stats")
                            team1_stats_df = scrape_team_basic_stats(soup, team1_abbr) # Pass the initial soup
                            if team1_stats_df is not None:
                                st.dataframe(team1_stats_df)


                            # Scrape and display stats for Team 2 (using the initial soup)
                            st.subheader(f"{team2_abbr} Basic Stats")
                            team2_stats_df = scrape_team_basic_stats(soup, team2_abbr) # Pass the initial soup
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

                # Process Team 1 stats for Top Scorers and Player of the Game
                # Ensure necessary columns exist for both sections
                required_cols_top_scorers = ['Starters', 'PTS']
                required_cols_pog = ['Starters', 'GmSc', 'TRB', 'AST', 'STL', 'BLK', 'PTS'] # Defined here for clarity

                if team1_stats_df is not None and team1_abbr:
                    if all(col in team1_stats_df.columns for col in required_cols_top_scorers):
                        team1_players_top_scorers = team1_stats_df[required_cols_top_scorers].copy()
                        team1_players_top_scorers = team1_players_top_scorers.rename(columns={'Starters': 'Player'})
                        team1_players_top_scorers['Team'] = team1_abbr
                        all_player_stats.append(team1_players_top_scorers)
                    else:
                        st.warning(f"Missing required columns for Top Scorers in {team1_abbr} stats.")


                # Process Team 2 stats for Top Scorers
                if team2_stats_df is not None and team2_abbr:
                    if all(col in team2_stats_df.columns for col in required_cols_top_scorers):
                        team2_players_top_scorers = team2_stats_df[required_cols_top_scorers].copy()
                        team2_players_top_scorers = team2_players_top_scorers.rename(columns={'Starters': 'Player'})
                        team2_players_top_scorers['Team'] = team2_abbr
                        all_player_stats.append(team2_players_top_scorers)
                    else:
                         st.warning(f"Missing required columns for Top Scorers in {team2_abbr} stats.")

                # Combine and sort stats for Top Scorers if data was collected
                if all_player_stats:
                    combined_df_top_scorers = pd.concat(all_player_stats, ignore_index=True)

                    # Convert 'PTS' to numeric, handling errors
                    combined_df_top_scorers['PTS'] = pd.to_numeric(combined_df_top_scorers['PTS'], errors='coerce').fillna(0)

                    # Sort by PTS descending
                    sorted_players_df_top_scorers = combined_df_top_scorers.sort_values(by='PTS', ascending=False)

                    # --- Filter for Top 5 with ties ---
                    if len(sorted_players_df_top_scorers) > 0:
                        if len(sorted_players_df_top_scorers) >= 5:
                            fifth_player_pts = sorted_players_df_top_scorers.iloc[4]['PTS']
                            top_scorers_df = sorted_players_df_top_scorers[sorted_players_df_top_scorers['PTS'] >= fifth_player_pts]
                        else:
                            top_scorers_df = sorted_players_df_top_scorers

                        st.dataframe(top_scorers_df)
                    else:
                        st.info("No player stats available to determine top scorers.")

                else:
                    st.info("Player stats could not be processed for Top Scorers.")


                # --- Player of the Game Section ---
                st.header("Player of the Game")

                pog_candidates_list = []

                # Process Team 1 stats for Player of the Game
                if team1_stats_df is not None and team1_abbr:
                    required_cols_pog = ['Starters', 'GmSc', 'TRB', 'AST', 'STL', 'BLK', 'PTS']
                    if all(col in team1_stats_df.columns for col in required_cols_pog):
                        # Select all required columns for POG consideration
                        team1_players_pog = team1_stats_df[required_cols_pog].copy()
                        team1_players_pog = team1_players_pog.rename(columns={'Starters': 'Player'})
                        pog_candidates_list.append(team1_players_pog)
                    else:
                         st.warning(f"Missing required columns for Player of the Game in {team1_abbr} stats.")


                # Process Team 2 stats for Player of the Game
                if team2_stats_df is not None and team2_abbr:
                    required_cols_pog = ['Starters', 'GmSc', 'TRB', 'AST', 'STL', 'BLK', 'PTS']
                    if all(col in team2_stats_df.columns for col in required_cols_pog):
                        # Select all required columns for POG consideration
                        team2_players_pog = team2_stats_df[required_cols_pog].copy()
                        team2_players_pog = team2_players_pog.rename(columns={'Starters': 'Player'})
                        pog_candidates_list.append(team2_players_pog)
                    else:
                         st.warning(f"Missing required columns for Player of the Game in {team2_abbr} stats.")


                # Determine and display Player of the Game if data was collected
                if pog_candidates_list:
                    combined_pog_candidates_df = pd.concat(pog_candidates_list, ignore_index=True)

                    # Convert 'GmSc' to numeric, handling errors
                    combined_pog_candidates_df['GmSc'] = pd.to_numeric(combined_pog_candidates_df['GmSc'], errors='coerce').fillna(0)

                    # Find the player with the highest Game Score
                    if len(combined_pog_candidates_df) > 0:
                        # Find index of the max GmSc
                        player_of_the_game_index = combined_pog_candidates_df['GmSc'].idxmax()

                        # Get the row for the Player of the Game
                        player_of_the_game_row = combined_pog_candidates_df.loc[player_of_the_game_index]

                        # Select and display the requested columns for POG
                        pog_display_cols = ['Player', 'TRB', 'AST', 'STL', 'BLK', 'PTS', 'GmSc'] # Include GmSc for context
                        player_of_the_game_stats = player_of_the_game_row[pog_display_cols]

                        # Convert the Series to a DataFrame for display
                        player_of_the_game_df = player_of_the_game_stats.to_frame().T # Transpose to get one row, multiple columns

                        st.dataframe(player_of_the_game_df)
                    else:
                        st.info("No player stats available to determine Player of the Game.")

                else:
                    st.info("Player stats could not be processed for Player of the Game.")


            except requests.exceptions.RequestException as e:
                st.error(f"Error fetching the URL: {e}")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

        else:
            st.error("Please enter a valid Box Score URL.")


if __name__ == "__main__":
    main()
