#!/usr/bin/env python3
"""Program's entry point."""
import logging
import logging.config
import sys
from logging import handlers

from .argparse_wrapper import get_arguments
from .constants import _DEFAULT_LOG_FORMAT, _DEFAULT_TIME_FORMAT
from .definitions import get_config, get_dict_config_from_yaml_file
# from .product_filter_runner import product_filter_live_runner
from .product_filter_runner import ProductFilterRunner


def main(argv=None):
    """Program's main routine."""
    args = get_arguments(argv)

    if args.logging_conf_file:
        logging.config.dictConfig(get_dict_config_from_yaml_file(args.logging_conf_file))
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt=_DEFAULT_LOG_FORMAT, datefmt=_DEFAULT_TIME_FORMAT)
    handler.setFormatter(formatter)
    logging.getLogger("").addHandler(handler)
    logging.getLogger("").setLevel(logging.DEBUG)
    logging.getLogger("posttroll").setLevel(logging.INFO)
    LOG = logging.getLogger("product_filter_runner")
    log_handlers = logging.getLogger("").handlers
    for log_handle in log_handlers:
        if type(log_handle) is handlers.SMTPHandler:
            LOG.debug("Mail notifications to: %s", str(log_handle.toaddrs))

    OPTIONS = get_config(args.config_file, args.service)
    # product_filter_live_runner(OPTIONS)
    LOG.info("Starting up.")
    try:
        prodf = ProductFilterRunner(OPTIONS)

    except Exception as err:
        LOG.error('Product Filter Runner crashed: %s', str(err))
        sys.exit(1)
    try:
        prodf.start()
        prodf.join()
    except KeyboardInterrupt:
        LOG.debug("Interrupting")
    finally:
        prodf.close()
