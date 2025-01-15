import subprocess
import time
import random
import os

# Define ranges and configurations
FILE_SIZE_RANGE = [128 * 1024, 512 * 1024, 1024 * 1024]  # 128KB, 512KB, 1MB
CONNECTION_COUNTS = [1, 2, 4, 8]

# ANSI color codes
class Colors:
    OKLAVENDER = '\033[38;5;216m'
    ENDC = '\033[0m'


def run_server():
    """Start the server as a subprocess."""
    return subprocess.Popen(["python", "Server.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_client(num_connections, file_size):
    """Start the client as a subprocess and collect its output."""
    process = subprocess.Popen(
        ["python", "Client.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Provide input to the client
    input_data = f"{num_connections}\n{num_connections}\n{file_size}\n"
    stdout, stderr = process.communicate(input=input_data)
    return stdout, stderr


def parse_client_output(output, num_connections):
    """Extract timing and speed information from the client output."""
    tcp_speed = []
    udp_speed = []
    tcp_times = []  # List to store individual TCP transfer times
    udp_times = []  # List to store individual UDP transfer times

    for line in output.splitlines():
        if "TCP transfer" in line and "finished" in line:
            try:
                # Extract TCP time and speed for each transfer
                time_part = next(p for p in line.split(",") if "total time" in p)
                tcp_times.append(float(time_part.split(":")[-1].strip().split()[0]))  # Time for each TCP transfer
                speed_part = next(p for p in line.split(",") if "total speed" in p)
                tcp_speed.append(float(speed_part.split(":")[-1].strip().split()[0]) / (1024 * 1024))  # Speed in MB/sec
            except (ValueError, StopIteration):
                pass

        elif "UDP transfer" in line and "finished" in line:
            try:
                # Extract UDP time and speed for each transfer
                time_part = next(p for p in line.split(",") if "total time" in p)
                udp_times.append(float(time_part.split(":")[-1].strip().split()[0]))  # Time for each UDP transfer
                speed_part = next(p for p in line.split(",") if "total speed" in p)
                udp_speed.append(float(speed_part.split(":")[-1].strip().split()[0]) / (1024 * 1024))  # Speed in MB/sec
            except (ValueError, StopIteration):
                pass

    # Calculate total time by summing the times for each transfer
    total_tcp_time = sum(tcp_times)  # Total time for all TCP transfers
    total_udp_time = sum(udp_times)  # Total time for all UDP transfers

    # Calculate mean speeds per connection
    if tcp_speed:
        mean_tcp_speed = sum(tcp_speed) / len(tcp_speed)
    else:
        mean_tcp_speed = 0

    if udp_speed:
        mean_udp_speed = sum(udp_speed) / len(udp_speed)
    else:
        mean_udp_speed = 0

    return mean_tcp_speed, mean_udp_speed, total_tcp_time, total_udp_time


def run_tests():
    """Run experiments for each file size and connection count."""
    print("Starting UDP vs TCP transfer comparison...\n")

    for file_size in FILE_SIZE_RANGE:
        for num_connections in CONNECTION_COUNTS:
            file_size_mb = file_size / (1024 * 1024)  # Convert to MB
            print(
                f"{Colors.OKLAVENDER}Test Settings: {num_connections} connections, File size: {file_size_mb:.2f} MB{Colors.ENDC}")

            server_process = run_server()
            time.sleep(1)  # Allow the server to start

            try:
                stdout, stderr = run_client(num_connections, file_size)
                if stderr:
                    print(f"Client Error: {stderr}")

                # Parse client output to get the speeds and times
                mean_tcp_speed, mean_udp_speed, total_tcp_time, total_udp_time = parse_client_output(stdout,
                                                                                                     num_connections)

                if mean_tcp_speed > 0 and mean_udp_speed > 0:
                    print(f"TCP transfer mean speed: {mean_tcp_speed:.2f} MB/sec, Total Time: {total_tcp_time:.4f} sec")
                    print(f"UDP transfer mean speed: {mean_udp_speed:.2f} MB/sec, Total Time: {total_udp_time:.4f} sec")

                    if mean_tcp_speed > mean_udp_speed:
                        print(f"TCP is faster than UDP in this test!\n")
                    else:
                        print(f"UDP is faster than TCP in this test!\n")
                else:
                    print("Error: Could not parse speeds from client output.")

            finally:
                server_process.terminate()
                server_process.wait()


def main():
    """Main entry point to run the tests."""
    run_tests()


if __name__ == "__main__":
    main()
