import streamlit as st
import requests
from bs4 import BeautifulSoup
from bs4.element import Comment # Import Comment
import pandas as pd

def scrape_line_score(url):
    """
    Scrapes the line score table from a basketball-reference.com URL.

    Args:
        url (str): The URL of the box score page.

    Returns:
        pandas.DataFrame or None: A DataFrame containing the line score data,
                                  or None if scraping fails or the table is not found.
    """
    try:
        # Send a GET request to the URL
        response = requests.get(url)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # Parse the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the table with the ID 'line_score'
        # basketball-reference often comments out tables, need to find the comment first
        # Check if the table is directly available or commented out
        line_score_table = soup.find('table', id='line_score')

        # If not found directly, search for commented out tables
        if not line_score_table:
             # Use the correct way to check for Comment type
             comments = soup.find_all(string=lambda text: isinstance(text, Comment))
             for comment in comments:
                 soup_comment = BeautifulSoup(comment, 'html.parser')
                 line_score_table = soup_comment.find('table', id='line_score')
                 if line_score_table:
                     break # Found the table in a comment


        if line_score_table:
            # Extract table headers
            headers = []
            # Look for the second tr in the thead, which contains the actual column headers
            header_row = line_score_table.select_one('thead tr:nth-of-type(2)')
            if header_row:
                 headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
                 # Clean up headers - '&nbsp;' might appear for the first column
                 headers = [h if h != '\xa0' else 'Team' for h in headers]


            # Extract table rows
            data = []
            for row in line_score_table.select('tbody tr'):
                row_data = [cell.get_text().strip() for cell in row.find_all(['th', 'td'])]
                data.append(row_data)

            # Create a pandas DataFrame
            if headers and data:
                 # Ensure headers and data rows have the same number of columns
                 # This can be tricky if rows have inconsistent numbers of cells,
                 # but for well-formed tables like this, it should be consistent.
                 # If not, padding or error handling might be needed.
                 # For now, assume consistency based on the provided HTML structure.
                df = pd.DataFrame(data, columns=headers)
                return df
            else:
                st.error("Could not extract headers or data from the line score table.")
                return None

        else:
            st.error("Could not find the line score table with ID 'line_score' on the page.")
            return None

    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching the URL: {e}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during scraping: {e}")
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

            # --- Team Trends Section ---
            st.header("Team Trends")
            # Call the scraping function
            line_score_df = scrape_line_score(box_score_url)

            # Display the line score table if successfully scraped
            if line_score_df is not None:
                st.subheader("Line Score")
                st.dataframe(line_score_df) # Use st.dataframe for interactive table

            else:
                # Error message is already displayed in the scrape_line_score function
                pass # Do nothing here


            # --- Placeholder Sections for other charts ---
            st.header("Top 5 Scorers")
            st.write("Chart/Table area for top 5 scorers will appear here.")
            st.warning("Scraping for player stats is not yet implemented.")


            st.header("Player of the Game")
            st.write("Section to highlight the Player of the Game.")
            st.warning("Logic for determining Player of the Game is not yet implemented.")


        else:
            st.error("Please enter a valid Box Score URL.")


if __name__ == "__main__":
    main()
