# Entry point for integration test.
# All system arguments are passed to the ``scicat_ingestor``.


if __name__ == "__main__":
    import signal
    import subprocess
    import sys
    from time import sleep

    # Run the main function in a subprocess
    command = (
        "scicat_ingestor",
        *(sys.argv[1:] or ["--verbose", "-c", "resources/config.sample.json"]),
    )
    process = subprocess.Popen(command)  #  noqa: S603

    # Send a SIGINT signal to the process after 5 seconds
    sleep(5)
    process.send_signal(signal.SIGINT)

    # Kill the process after 5 more seconds
    sleep(5)
