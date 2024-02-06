# pate-trigger-sv-mgr

pate-trigger (Palworld)'s dedicated server auto restarter in async python for mitigating memory leak.

There is also an attempt to backup your save data.

## How use

1. Clone the project
1. `pipenv install`
1. Get the dedicated server files
1. Put the two `.bat` files there
1. Configure the server options in the `Start server.bat` file
1. Configure the constants at around the top of `main.py` file
1. Rename `secrets.template.json` back to `secrets.json`
1. Configure `secrets.json` if you want use discord webhook to log
    1. If don't use, comment out its `addHandler` in `setup_server` function in `LoggingStuff.py`
1. Run `main.py`

## What do

- Restart the server process:
    - Immediately if it dies unexpectedly
    - After a configured amount of time, with a warning sent:
        - Been running for too long (process uptime limit)
        - Leaked too much memory (process memory limit)
- Run the backup script:
    - Every configured interval
    - When the server dies
- Upload the backup data:
    - When the server dies

> **_NOTE:_**  The server process does take more memory for the more users logged in simultaneously, does not neccessarily mean that it leaked memory. You will need to observe the resource usage a few times, and determine what should be the limits including your own device hardware specs in mind.

> **_note:_**  If the backup job is run due to interval, it will only upload the log file. Only when the server dies will it also upload the backup save data file.

## Requirements

### Required

- pipenv
- Python 3.12

### These can be statisfied using your own alternatives or disable entirely

- WinRAR executable `Rar.exe` for save archiving
- Discord webhook and a role id to ping
- Whatever version of the pate-trigger dedicated server files
- The two starters batch file
    - One to start the server with recommended arguments
    - Another one to configure save data archiving
- The upload of the save data archiving process log file and its resulting data file to webhook

### Windows

- It is not cross-platform due to these problems:
    - The signal sent to terminate the process gracefully is incompatible on Windows/Linux
    - The starter batch files and archiving with `WinRAR`

## License

MIT

## Contribution

Feel free

## More

There is an useless log file because I forgot to gitignore it the when I created the repo.