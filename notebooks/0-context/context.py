import os
import numpy as np
import pandas as pd
import logging

from matmat.utils import logging as log, config
config.LOGGER_LEVEL=logging.INFO
config.VERBOSE = True
log.configure_logging()