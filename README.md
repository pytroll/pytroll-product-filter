# pytroll-product-filter

### About

Take a (EUMETCast disseminated) satellite product file and send it on to a
configurable set of destinations if it covers a configurable area of
interest. Uses only the filename to determine the coverage, thus requiring at a
minimum the platform name and the start time (and preferably also the end time)
in the filename.

### System Requirements

* python >=3.9
* **Only for
[Developer-Mode Installtion](#developer-mode-installation):**
  * [`poetry`](https://python-poetry.org), installed as follows:

                curl -sSL https://install.python-poetry.org | python3 -
  * [`poetry-dynamic-versioning`](https://github.com/mtkennerly/poetry-dynamic-versioning),
    to be installed **after** you install `poetry`:

                poetry self add "poetry-dynamic-versioning[plugin]"


### Installation

#### Developer Mode Installation

:point_right: For those who need/wish to make changes to `deode`'s
source code, or use code from a different branch than `master`.

    poetry install

Installing in "developer mode" means that changes made in any of the package's
source files become visible as soon as the package is reloaded.

If you have problems installing `poetry`, you can install in development mode using `pip (>= v22.2.2)` as follows:

    pip install -e .

##### Regular Installation From Downloaded Source

:point_right: For those who have `deode`'s source code in a local directory,
wish to install it from there, but also don't want to modify any code.

    pip install .

