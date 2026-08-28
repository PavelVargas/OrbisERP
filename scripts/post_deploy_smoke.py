#!/usr/bin/env python3
import argparse
import sys
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True, help='Ej. https://erp.example.com')
    parser.add_argument('--timeout', type=float, default=5.0)
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    failures = []
    for path, expected in [('/operations/health/live', 200), ('/operations/health/ready', 200)]:
        try:
            response = requests.get(base + path, timeout=args.timeout)
            data = response.json()
            print(path, response.status_code, data)
            if response.status_code != expected:
                failures.append(path)
        except Exception as exc:
            print(path, 'ERROR', exc)
            failures.append(path)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
