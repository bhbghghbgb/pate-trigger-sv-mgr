import asyncio
import datetime
import signal
import subprocess
import time

import psutil

from LoggingStuff import CODENAME, logger, setup_logging, webhook_file_upload

PROCESS_NAME = "PalServer-Win64-Test-Cmd.exe"
PROCESS_EXECUTOR = "F:/Volume 1/gem/Palworld/_Dedicated Server/Start sv.bat"
PROCESS_EXECUTOR_CWD = "F:/Volume 1/gem/Palworld/_Dedicated Server"
PROCESS_DATA_BACKUP_EXECUTOR = (
    "F:/Volume 1/gem/Palworld/_Dedicated Server/Backup save.bat"
)
PROCESS_DATA_BACKUP_EXECUTOR_LOG = (
    "F:/Volume 1/gem/Palworld/_Dedicated Server/Backup save.log"
)
PROCESS_DATA_BACKUP_DATA = "F:/Volume 1/gem/Palworld/_Dedicated Server/Saved.rar"
PROCESS_MAX_MEM = 9 * 1024 * 1024 * 1024
PROCESS_MAX_LIVE_TIME = 3600
PROCESS_MONITOR_INTERVAL = 60
PROCESS_PRIOR_KILL_TIME = 90
PROCESS_PRIOR_KILL_LAST_WARNING_TIME = 10
STATISTICS_LOG_INTERVAL = 60

script_start_timepoint = time.time()
process_restart_timepoint = 0
process_start_count = 0
process_object: psutil.Process | None = None
process_parent_subprocess: asyncio.subprocess.Process | None = None
# allow a few moments for the process to start before logging
last_statistics_log_timepoint = time.time() - STATISTICS_LOG_INTERVAL + 10


async def main():
    global statistics_log_task
    setup_logging()
    try:
        on_script_start()
        statistics_log_task = asyncio.create_task(statistics_log_loop())
        try:
            while True:
                for _ in range(3):
                    if await restart_process() is None:
                        logger.warning(
                            "The process didn't feel like starting, retrying in 3s"
                        )
                        await asyncio.sleep(3)
                    else:
                        break
                else:
                    logger.critical("The process doesn't want to start")
                    break
                statistics_log()
                wait_process_unexpected_death_task = asyncio.create_task(
                    wait_process_unexpected_death()
                )
                process_monitor_loop_task = asyncio.create_task(process_monitor_loop())
                # return when either the process died unexpectedly, or it's not healthy and past the warning time
                await asyncio.wait(
                    [wait_process_unexpected_death_task, process_monitor_loop_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
        except KeyboardInterrupt:
            logger.info("Requested monitor termination", exc_info=True)
            on_script_stop()
            raise
    except Exception:
        logger.critical("Unhandled exception", exc_info=True)
        raise
    on_script_stop()


async def wait_process_unexpected_death():
    global process_parent_subprocess, process_object
    try:
        if process_parent_subprocess is not None:
            return_code = await process_parent_subprocess.wait()
            logger.error("Process died unexpectedly, return code %d", return_code)
            # finishes the task here to trigger restart_process in main()
    except asyncio.CancelledError:
        logger.debug("Process wait for unexpected death cancelled")
    finally:
        process_parent_subprocess = None
        process_object = None


async def process_monitor_loop():
    try:
        while True:
            healthy_status = get_process_is_healthy()
            if not all(healthy_status):
                await warn_before_process_kill(healthy_status)
                return  # finishes the task here to trigger restart_process in main()
            await asyncio.sleep(PROCESS_MONITOR_INTERVAL)
    except asyncio.CancelledError:
        logger.debug("Process monitor loop cancelled")


async def warn_before_process_kill(healthy_status):
    statistics_log()
    logger.warning(
        "Process is not healthy %s, restart in %s (%s)",
        healthy_status,
        humanize_duration(PROCESS_PRIOR_KILL_TIME),
        discordize_timestamp_relative_to_now(PROCESS_PRIOR_KILL_TIME),
    )
    await asyncio.sleep(PROCESS_PRIOR_KILL_TIME - PROCESS_PRIOR_KILL_LAST_WARNING_TIME)
    logger.warning(
        "Process kill in %s",
        humanize_duration(PROCESS_PRIOR_KILL_LAST_WARNING_TIME),
    )
    await asyncio.sleep(PROCESS_PRIOR_KILL_LAST_WARNING_TIME)


def discordize_timestamp_relative(seconds_since_epoch: float):
    return f"<t:{int(seconds_since_epoch)}:R>"


def discordize_timestamp_relative_to_now(seconds: float):
    return discordize_timestamp_relative(time.time() + seconds)


async def restart_process():
    process = get_process()
    if process is not None:
        logger.info("Asking the process to shutdown gracefully")
        graceful_die_result = await process_graceful_kill(process)
        if not graceful_die_result[0]:
            logger.error("Killing process (Graceful shutdown timed out)")
            await process_force_kill(process)
    await on_after_process_death()
    await on_before_process_restart()
    logger.info("Starting process")
    return await start_process()


async def start_process():
    global process_restart_timepoint, process_start_count, process_parent_subprocess
    process_parent_subprocess = await asyncio.create_subprocess_exec(
        PROCESS_EXECUTOR,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=PROCESS_EXECUTOR_CWD,
    )
    process_restart_timepoint = time.time()
    process_start_count += 1
    return await wait_process_start()


async def process_graceful_kill(process: psutil.Process):
    # send a few signals to ensure we pass the "Terminate batch job" prompt
    try:
        # doesn't work
        if process_parent_subprocess is not None:
            for _ in range(3):
                process_parent_subprocess.send_signal(signal.CTRL_BREAK_EVENT)
                await asyncio.sleep(0.1)
    except OSError:
        pass
    return await asyncio.get_running_loop().run_in_executor(
        None, lambda process=process: wait_process_graceful_kill(process)
    )


async def process_force_kill(process: psutil.Process):
    process.kill()
    await asyncio.sleep(1)


def wait_process_graceful_kill(
    process: psutil.Process,
) -> tuple[bool, int | None]:  # (succeeded?, return code)
    try:
        return_code = process.wait(3)
        return True, return_code
    except psutil.TimeoutExpired:
        return False, None


def get_process_is_healthy() -> tuple[bool, bool, bool]:
    global process_memory_info_cached
    process_memory_info = process_memory_info_cached
    if process_memory_info is None:
        return False, False, False
    return (
        True,
        process_memory_info[0] < PROCESS_MAX_MEM,
        get_process_uptime() < PROCESS_MAX_LIVE_TIME,
    )


def get_process_uptime():
    return time.time() - process_restart_timepoint


async def statistics_log_loop():
    global last_statistics_log_timepoint
    while True:
        seconds_since_last_log = time.time() - last_statistics_log_timepoint
        if seconds_since_last_log >= STATISTICS_LOG_INTERVAL:
            statistics_log()
            await asyncio.sleep(STATISTICS_LOG_INTERVAL)
            continue
        await asyncio.sleep(STATISTICS_LOG_INTERVAL - seconds_since_last_log)


def statistics_log():
    global last_statistics_log_timepoint
    virtual_memory_used, virtual_memory_total, swap_memory_used, swap_memory_total = (
        get_system_memory_info()
    )
    process_memory_info = get_process_memory_info()
    process_memory_virtual, process_memory_resident = (
        process_memory_info if process_memory_info is not None else (-1, -1)
    )
    process_pid = (
        (process_object.pid, process_object.ppid())
        if process_object is not None
        else None
    )
    logger.info(
        "System memory: Virtual %s/%s, Swap %s/%s"
        "\n> Process memory: Virtual %s/%s, Resident %s"
        "\n> Process uptime %s/%s, start count %d, pid %s"
        "\n> Script uptime %s"
        "\n> Healthiness %s",
        humanize_size(virtual_memory_used),
        humanize_size(virtual_memory_total),
        humanize_size(swap_memory_used),
        humanize_size(swap_memory_total),
        humanize_size(process_memory_virtual),
        humanize_size(PROCESS_MAX_MEM),
        humanize_size(process_memory_resident),
        humanize_duration(get_process_uptime()),
        humanize_duration(PROCESS_MAX_LIVE_TIME),
        process_start_count,
        process_pid,
        humanize_duration(time.time() - script_start_timepoint),
        get_process_is_healthy(),
    )
    last_statistics_log_timepoint = time.time()


def humanize_duration(seconds: float):
    return str(datetime.timedelta(seconds=int(seconds)))


def get_system_memory_info():
    virtual_memory = psutil.virtual_memory()
    virtual_memory_used = virtual_memory.used
    virtual_memory_total = virtual_memory.total
    swap_memory = psutil.swap_memory()
    swap_memory_used = swap_memory.used
    swap_memory_total = swap_memory.total
    return (
        virtual_memory_used,
        virtual_memory_total,
        swap_memory_used,
        swap_memory_total,
    )


def get_process_memory_info():
    global process_memory_info_cached
    process = get_process()
    if process is None:
        return None
    process_memory_info = process.memory_info()
    process_memory_resident = process_memory_info.rss
    process_memory_virtual = process_memory_info.vms
    # cache
    return (
        process_memory_info_cached := (process_memory_virtual, process_memory_resident)
    )


process_memory_info_cached = get_process_memory_info()


def get_process() -> psutil.Process | None:
    global process_object, process_parent_subprocess
    if (
        process_object is None or not process_object.is_running()
    ) and process_parent_subprocess is not None:
        for process in psutil.Process(process_parent_subprocess.pid).children(True):
            if process.name() == PROCESS_NAME:
                process_object = process
                return process
        return None
    return process_object


async def wait_process_start():
    for _ in range(3):
        if (
            process_object := await asyncio.get_running_loop().run_in_executor(
                None, get_process
            )
        ) is None:
            await asyncio.sleep(1)
        else:
            return process_object
    return None


async def on_before_process_restart():
    pass
    # logger.info("Uploading process save data on before process restart")
    # try:
    #     await webhook_file_upload(PROCESS_DATA_BACKUP_DATA)
    # except OSError:
    #     logger.exception("Cannot upload process save data on before process restart")


async def on_after_process_death():
    logger.info("Running backup subprocess on after process death")
    process = await asyncio.create_subprocess_exec(
        PROCESS_DATA_BACKUP_EXECUTOR,
        stderr=asyncio.subprocess.STDOUT,
        stdout=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=PROCESS_EXECUTOR_CWD,
    )
    await process.wait()
    try:
        if process.stdout is not None:
            with open(PROCESS_DATA_BACKUP_EXECUTOR_LOG, "wb") as f:
                f.write((await process.communicate())[0])
        await webhook_file_upload(
            [PROCESS_DATA_BACKUP_EXECUTOR_LOG, PROCESS_DATA_BACKUP_DATA]
        )
    except OSError:
        logger.exception(
            "Cannot upload data of backup subprocess on after process death"
        )


def on_script_start():
    logger.info("%s @sechnaptien mo sv OPEN", CODENAME)


def on_script_stop():
    logger.info("%s @Trà Lục Dạ Hy nghi di a oi", CODENAME)


# https://stackoverflow.com/questions/1094841/get-human-readable-version-of-file-size
def humanize_size(num, suffix="B"):
    for unit in ("", "Ki", "Mi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Gi{suffix}"


if __name__ == "__main__":
    asyncio.run(main())
