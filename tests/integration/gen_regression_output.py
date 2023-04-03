#
# Copyright 2019, 2023 Delphix
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring

import argparse
import cProfile

from tests.integration.infra import generate_regression_output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate regression output for test-suite")
    parser.add_argument('--profile',
                        action='store_true',
                        help='run with cProfile to identify bottlenecks')
    args = parser.parse_args()
    if args.profile:
        cProfile.run('generate_regression_output()')
    else:
        generate_regression_output()


if __name__ == '__main__':
    main()
