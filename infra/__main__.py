"""Build inventory-bound tools; deploy through infra.durable and infra.durable_ops."""

import argparse
import sys
from pathlib import Path

from infra import release
from infra.spec import load, log_groups, metric_catalog
from infra.verify import VerificationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="Build both inventory-bound read-only tools")
    build_parser.add_argument("--spec", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--wheelhouse", type=Path, required=True)
    iam_parser = commands.add_parser(
        "bootstrap-iam",
        help="Write the CloudFormation template that creates the roles named in deployment.json",
    )
    iam_parser.add_argument("--spec", type=Path, required=True)
    iam_parser.add_argument("--output", type=Path, required=True)
    iam_parser.add_argument(
        "--operator-trust",
        action="append",
        help="Principal ARN that may assume the operator role (repeatable)",
    )
    iam_parser.add_argument(
        "--ui-trust", action="append", help="Principal ARN that may assume the UI principal role (repeatable)"
    )
    iam_parser.add_argument(
        "--agentcore", action="store_true", help="Also allow the AgentCore runtime stages"
    )
    iam_parser.add_argument(
        "--instance-role", action="store_true", help="Also create the instance role and profile for the agent"
    )
    args = parser.parse_args()
    if args.command == "bootstrap-iam":
        try:
            from infra import bootstrap_iam

            spec = load(args.spec)
            template = bootstrap_iam.render(
                spec,
                operator_trust=args.operator_trust,
                ui_trust=args.ui_trust,
                agentcore=args.agentcore,
                instance_role=args.instance_role,
            )
            release.write_json(args.output, template)
        except (VerificationError, ValueError, KeyError, OSError) as exc:
            print(f"IAM template failed ({type(exc).__name__}); nothing was written to AWS.", file=sys.stderr)
            return 1
        print(
            f"Wrote {args.output}. As an AWS administrator, deploy it once in {spec['monitor_region']}:\n"
            f"  aws cloudformation deploy --template-file {args.output} "
            f"--stack-name {spec['project']}-{spec['environment']}-iam --capabilities CAPABILITY_NAMED_IAM "
            f"--region {spec['monitor_region']}"
        )
        return 0
    try:
        from scripts.build_lambdas import FUNCTIONS, build

        spec = load(args.spec)
        args.output.mkdir(parents=True, exist_ok=True)
        release.write_json(args.output / "metric-catalog.json", metric_catalog(spec))
        release.write_json(args.output / "log-scope.json", log_groups(spec))
        build(
            FUNCTIONS,
            args.output,
            args.output / "metric-catalog.json",
            args.wheelhouse,
            args.output / "log-scope.json",
        )
        return 0
    except (VerificationError, ValueError, KeyError, OSError) as exc:
        print(f"Tool build failed ({type(exc).__name__}); no deployment occurred.", file=sys.stderr)
        if isinstance(exc, VerificationError):
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
