import argparse
import sys

import onnxruntime
from piper.__main__ import main as piper_main


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--random-seed", type=int, required=True)
    arguments, piper_arguments = parser.parse_known_args()

    onnxruntime.set_seed(arguments.random_seed)
    sys.argv = [sys.argv[0], *piper_arguments]
    piper_main()


if __name__ == "__main__":
    main()
