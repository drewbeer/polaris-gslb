#!/bin/bash

# Example script that simulates health check behavior
TARGET_IP=$1

# Simulate a check
if ping -c 1 -W 1 $TARGET_IP > /dev/null; then
    echo "success"
    exit 0
else
    echo "failure"
    exit 1
fi
