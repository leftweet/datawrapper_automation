import streamlit as st
import requests
from bs4 import BeautifulSoup
from bs4.element import Comment # Import Comment
import pandas as pd

def find_table_in_soup(soup, table_id):
    """
    Finds a table by its ID within a BeautifulSoup object,
    checking both direct presence and commented-out sections.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the page.
        table_id (str): The ID of the table to find.

    Returns:
        BeautifulSoup tag or None: The table element if found, otherwise None.
    """
    # Try to find the table directly
    table = soup.find('table', id=table_id)

    # If not found directly, search within commented-out tables
    if not table:
         comments = soup.find_all(string=lambda text: isinstance(text, Comment))
         for comment in comments:
             comment_soup = BeautifulSoup(comment, 'html.parser')
             table = comment_soup.find('table', id=table_id)
             if table:
                 break # Found the table in a comment

    return table


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
    line_score_table = find_table_in_soup(soup, table_id)

    if line_score_table:
        try:
            # Extract table headers
            headers = []
            header_row = line_score_table.select_one('thead tr:nth-of-type(2)')
            if header_row:
                 headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
                 headers = [h if h != '\xa0' else 'Team' for h in headers] # Clean header

            # Extract table rows
            data = []
            for row in line_score_table.select('tbody tr'):
                row_data = [cell.get_text().strip() for cell in row.find_all(['th', 'td'])]
                data.append(row_data)

            if headers and data:
                df = pd.DataFrame(data, columns=headers)
                return df
            else:
                st.warning(f"Could not extract headers or data from the '{table_id}' table.")
                return None
        except Exception as e:
            st.error(f"Error parsing '{table_id}' table: {e}")
            return None
    else:
        st.warning(f"Could not find the '{table_id}' table on the page.")
        return None


def scrape_team_basic_stats(soup, team_abbr):
    """
    Scrapes the basic box score stats table for a specific team.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the page.
        team_abbr (str): The abbreviation of the team (e.g., 'CLE', 'MIA').

    Returns:
        pandas.DataFrame or None: A DataFrame containing the team's basic stats,
                                  or None if the table is not found or parsing fails.
    """
    table_id = f'box-{team_abbr}-game-basic' # Construct the ID
    # Note: The table itself doesn't have the 'div_' prefix in its ID,
    # but the surrounding div does. We need the table ID.
    # Based on the screenshot and typical basketball-reference structure, the table ID is 'box-TEAMABBR-game-basic'.

    team_stats_table = find_table_in_soup(soup, table_id)


    if team_stats_table:
        try:
            # Extract table headers
            headers = []
            # The main headers are typically in the third tr of the thead
            header_row = team_stats_table.select_one('thead tr:nth-of-type(3)')
            if header_row:
                 # Exclude the 'Starters' header and get subsequent th/td
                 headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]


            # Extract table rows (player stats)
            data = []
            for row in team_stats_table.select('tbody tr'):
                # Skip rows that might be subtotals or dividers if necessary,
                # but for basic stats table, tbody rows are usually players.
                row_data = [cell.get_text().strip() for cell in row.find_all(['th', 'td'])]
                data.append(row_data)

            if headers and data:
                 # Ensure consistent column count - sometimes last column (Plus/Minus) is missing
                 # for some rows if player didn't play. Pad with None if needed.
                 max_cols = len(headers)
                 padded_data = [row + [None] * (max_cols - len(row)) for row in data]
                 df = pd.DataFrame(padded_data, columns=headers)
                 return df
            else:
                st.warning(f"Could not extract headers or data from the '{table_id}' table.")
                return None
        except Exception as e:
            st.error(f"Error parsing '{table_id}' table: {e}")
            return None
    else:
        st.warning(f"Could not find the '{table_id}' table on the page.")
        return None


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
    if process_button_pressed:
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
                line_score_df = scrape_line_score(soup)

                if line_score_df is not None:
                    st.subheader("Line Score")
                    st.dataframe(line_score_df)

                    # Check if we have enough rows in the line score for two teams
                    if len(line_score_df) >= 2:
                        team1_abbr = line_score_df.iloc[0, 0] # Team abbr from the first row, first column
                        team2_abbr = line_score_df.iloc[1, 0] # Team abbr from the second row, first column

                        # Scrape and display stats for Team 1
                        st.subheader(f"{team1_abbr} Basic Stats")
                        team1_stats_df = scrape_team_basic_stats(soup, team1_abbr)
                        if team1_stats_df is not None:
                            st.dataframe(team1_stats_df)
                        else:
                             st.warning(f"Could not scrape basic stats for {team1_abbr}.")


                        # Scrape and display stats for Team 2
                        st.subheader(f"{team2_abbr} Basic Stats")
                        team2_stats_df = scrape_team_basic_stats(soup, team2_abbr)
                        if team2_stats_df is not None:
                            st.dataframe(team2_stats_df)
                        else:
                            st.warning(f"Could not scrape basic stats for {team2_abbr}.")

                    else:
                        st.warning("Line score does not contain data for two teams to scrape individual stats.")

                else:
                    st.warning("Could not display line score. Cannot proceed to scrape team stats.")


                # --- Placeholder Sections for other charts ---
                st.header("Top 5 Scorers")
                st.write("Chart/Table area for top 5 scorers will appear here.")
                st.warning("Scraping for advanced player stats or calculating top scorers is not yet implemented.")


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
