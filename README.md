# VRP Solver and Testing Platform

## Description

This project provides a web-based platform for solving Vehicle Routing Problems (VRP) using a checkpoint-based approach, as well as analysing different routing strategies. It includes features for location clustering, checkpoint generation, static VRP solving, and dynamic VRP testing with real-time insertions.

## Features

*   **Map Picker:** Interactively select warehouse and destination locations on a map. Save and load location presets.
*   **Location Clustering:** Apply clustering to group nearby locations. Visualise clusters and noise points.
*   **Checkpoint Generation:** Generate potential security checkpoints based on road network intersections near clusters.
*   **VRP Solver:** Solve static VRP instances using algorithms like Nearest Neighbor + 2-Opt and Google OR-Tools.
*   **VRP Testing Dashboard:**
    *   Run VRP scenarios using saved database snapshots.
    *   Compare different algorithms (OR-Tools vs. Heuristics) for checkpoint-based routing.
    *   Simulate dynamic P/D (Pickup/Delivery) insertions into existing routes and compare insertion strategies.
    *   Visualise routes, clusters, and checkpoints on an interactive map.

## Technologies Used

*   **Backend:** Python, Flask, SQLAlchemy
*   **Routing & Optimization:** Google OR-Tools, OpenRouteService (ORS) API, OSMnx, NetworkX
*   **Frontend:** HTML, CSS, JavaScript, Leaflet.js, Bootstrap
*   **Database:** SQLite
