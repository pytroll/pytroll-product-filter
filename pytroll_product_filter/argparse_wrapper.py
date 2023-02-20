#!/usr/bin/env python3
"""Wrappers for argparse functionality."""
import argparse
import sys


def get_arguments(argv=None):
    """Return parsed command line arguments."""

    if argv is None:
        argv = sys.argv[1:]

    def validate_config_file_name(config_file_name):
        config_file_name = str(config_file_name)
        if "template" in config_file_name.lower():
            raise ValueError("Cannot accept a template file as master config.")
        return config_file_name

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config_file",
        type=validate_config_file_name,
        dest="config_file",
        required=True,
        help="The file containing "
        + "configuration parameters e.g. product_filter_config.yaml",
    )
    parser.add_argument(
        "-s",
        "--service",
        help="Name of the service (e.g. iasi-lvl2)",
        dest="service",
        type=str.lower,
        required=True,
    )
    parser.add_argument(
        "-l",
        "--logging",
        help="The path to the log-configuration file (e.g. './log_config.yaml')",
        dest="logging_conf_file",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-v", "--verbose", help="print debug messages too", action="store_true"
    )

    return parser.parse_args(argv)
