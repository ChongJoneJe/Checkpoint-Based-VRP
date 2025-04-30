# VRP Solver and Testing Platform

## Description

This project provides a web-based platform for solving Vehicle Routing Problems (VRP) and analyzing different routing strategies. It includes features for location clustering, checkpoint generation, static VRP solving, and dynamic VRP testing with real-time insertions.

## Features

*   **Map Picker:** Interactively select warehouse and destination locations on a map. Save and load location presets.
*   **Location Clustering:** Apply DBSCAN clustering to group nearby locations. Visualize clusters and noise points.
*   **Checkpoint Generation:** Generate potential security checkpoints based on road network intersections near clusters.
*   **VRP Solver:** Solve static VRP instances using algorithms like Nearest Neighbor + 2-Opt and Google OR-Tools.
*   **VRP Testing Dashboard:**
    *   Run VRP scenarios using saved database snapshots.
    *   Compare different algorithms (OR-Tools vs. Heuristics) for checkpoint-based routing.
    *   Simulate dynamic P/D (Pickup/Delivery) insertions into existing routes and compare insertion strategies.
    *   Visualize routes, clusters, and checkpoints on an interactive map.

## Technologies Used

*   **Backend:** Python, Flask, SQLAlchemy
*   **Routing & Optimization:** Google OR-Tools, OpenRouteService (ORS) API, OSMnx, NetworkX
*   **Clustering:** Scikit-learn (DBSCAN)
*   **Frontend:** HTML, CSS, JavaScript, Leaflet.js, Bootstrap
*   **Database:** SQLite

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(Requires Python 3.10.0 as specified in `requirements.txt`)*

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: `matplotlib` is listed but might not be directly used by the web app itself. `ortools` installation might vary based on OS/Python version.)*

4.  **Configure API Key:**
    *   Obtain an API key from [OpenRouteService](https://openrouteservice.org/).
    *   Create or update the `config.py` file and add your key:
        ```python
        # config.py
        ORS_API_KEY = 'YOUR_ORS_API_KEY'
        # Other configurations...
        DATABASE_URI = 'sqlite:///../instance/app.db'
        ```

5.  **Initialize Database:**
    *   The application uses SQLite. The database file (`app.db`) will typically be created automatically in an `instance` folder when the app first runs and needs it.
    *   If you need to reset the database schema, you might use the `reset_db.py` script (if it's designed for schema creation):
        ```bash
        python reset_db.py
        ```

## Running the Application

1.  **Ensure your virtual environment is activated.**
2.  **Start the Flask Development Server:**
    ```bash
    flask run
    ```
    *(Alternatively, if `app.py` has `if __name__ == '__main__': app.run(...)`, you can use `python app.py`)*
3.  **Open your web browser** and navigate to `http://127.0.0.1:5000` (or the address provided by Flask).

## Project Structure

```
├── .gitignore          # Specifies intentionally untracked files that Git should ignore
├── app.py              # Main Flask application setup and initialization
├── config.py           # Configuration settings (API keys, database URI)
├── README.md           # This file
├── requirements.txt    # Python dependencies
├── reset_db.py         # Script to reset/initialize the database (if applicable)
├── save_db.py          # Script to save database snapshots for testing
│
├── algorithms/         # Core VRP, TSP, clustering, and network analysis logic
├── cache/              # Caching directory (e.g., for OSMnx network data)
├── instance/           # Flask instance folder (often contains the SQLite DB - should be gitignored)
├── models/             # SQLAlchemy database models (Location, Cluster, Preset)
├── repositories/       # Data access layer (interacts with the database)
├── routes/             # Flask Blueprints defining application routes/endpoints
├── services/           # Business logic layer, orchestrates operations
├── static/             # Frontend assets (CSS, JavaScript, images)
├── templates/          # HTML templates (rendered by Flask)
├── utils/              # Utility functions (database helpers, etc.)
└── vrp_test_data/      # Directory for storing database snapshots used in testing
```