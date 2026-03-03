#!/bin/sh
set -e
service ssh start
exec conda run -n alliantieai streamlit run "./webapp_src/Alliantie_AI.py" --server.port=8080