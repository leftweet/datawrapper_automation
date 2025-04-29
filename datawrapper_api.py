import requests
import json
import os
import csv

def create_chart_from_csv(csv_path: str, api_token: str) -> str:
    BASE_URL = 'https://api.datawrapper.de/v3'
    HEADERS_JSON = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json'
    }
    HEADERS_CSV = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'text/csv'
    }

    # Step 1: Read column headers
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file '{csv_path}' not found.")

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=',')
        headers = next(reader)

    if len(headers) < 3:
        raise ValueError("CSV must have at least 3 columns")

    x_axis_col = headers[0]
    team_a_col = headers[1]
    team_b_col = headers[2]

    # Step 2: Create the chart
    chart_config = {
        "title": f"{team_a_col} vs. {team_b_col} Game Flow",
        "type": "d3-lines"
    }

    response = requests.post(f"{BASE_URL}/charts", headers=HEADERS_JSON, data=json.dumps(chart_config))
    response.raise_for_status()
    chart_id = response.json()['id']

    # Step 3: Upload CSV data
    with open(csv_path, 'r', encoding='utf-8') as file:
        csv_data = file.read()

    upload_url = f"{BASE_URL}/charts/{chart_id}/data"
    upload_response = requests.put(upload_url, headers=HEADERS_CSV, data=csv_data.encode('utf-8'))
    upload_response.raise_for_status()

    # Step 4: Patch metadata
    metadata_url = f"{BASE_URL}/charts/{chart_id}"
    metadata_patch = {
        "metadata": {
            "describe": {
                "source-name": "Basketball Reference",
                "source-url": "",
                "intro": "",
                "byline": "",
                "aria-description": "",
                "number-format": "-",
                "number-divisor": 0,
                "number-append": "",
                "number-prepend": ""
            },
            "visualize": {
                "dark-mode-invert": True,
                "lines": {
                    team_a_col: {
                        "symbols": {
                            "on": "last",
                            "style": "hollow",
                            "enabled": True
                        },
                        "valueLabels": {
                            "first": False,
                            "enabled": True
                        }
                    },
                    team_b_col: {
                        "symbols": {
                            "on": "last",
                            "style": "hollow",
                            "enabled": True
                        },
                        "valueLabels": {
                            "first": False,
                            "enabled": True
                        }
                    }
                },
                "custom-area-fills": [
                    {
                        "id": "0Av44dodX1",
                        "to": team_b_col,
                        "from": team_a_col,
                        "color": "#cccccc",
                        "opacity": 0.3,
                        "colorNegative": "#E31A1C",
                        "interpolation": "linear",
                        "useMixedColors": False
                    }
                ],
                "connector-lines": True,
                "interpolation": "monotone-x",
                "hover-highlight": True,
                "plotHeightFixed": 350,
                "show-color-key": False
            }
        }
    }

    patch_response = requests.patch(metadata_url, headers=HEADERS_JSON, data=json.dumps(metadata_patch))
    patch_response.raise_for_status()

    # Step 5: Publish chart
    publish_url = f"{BASE_URL}/charts/{chart_id}/publish"
    publish_response = requests.post(publish_url, headers={'Authorization': f'Bearer {api_token}'})
    publish_response.raise_for_status()

    # Step 6: Return chart URL
    return f"https://www.datawrapper.de/_/{chart_id}"
