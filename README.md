# pate-trigger-sv-mgr

pate-trigger (Palworld)'s dedicated server auto restarter in async python for mitigating memory leak.

## How use

1. Clone the project
1. `pipenv shell`
1. Get the dedicated server files
1. Put the two `.bat` files there
1. Configure the constants at around the top of `main.py` file
1. Configure `secrets.json` if you want use discord webhook to log
    1. If don't use, comment out its `addHandler` in `setup_server` function in `LoggingStuff.py`

## License

MIT

## Contribution

Feel free