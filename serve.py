"""Run the local WSGI server; production settings come from environment variables."""

import argparse

from waitress import serve

from config.wsgi import application

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    serve(application, host=arguments.host, port=arguments.port, threads=4)
