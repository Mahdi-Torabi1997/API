# AltumView Record Parser

## Overview

A Python script to fetch and parse skeletal data from AltumView's recorded footage, using `requests` for API interaction and `pandas` for data handling.

## Features

- Authenticates and fetches data from AltumView API.
- Parses binary recording data to extract skeletal information.
- Exports parsed data to a CSV file for analysis.

## How to Use

1. **Authentication**: Set your `CLIENT_ID` and `CLIENT_SECRET`.
2. **Fetching Records**: Specify the date range and camera IDs.
3. **Data Parsing and Exporting**: Run the script to parse data and save it as a CSV file.
