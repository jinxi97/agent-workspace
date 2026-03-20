"""Shared Pulumi mock setup for all tests.

set_mocks can only be called once per process, so this conftest
initializes it before any test module is imported.
"""

import asyncio

import pulumi

asyncio.set_event_loop(asyncio.new_event_loop())


class MockGcp(pulumi.runtime.Mocks):
    """Mock GCP provider – returns inputs as outputs with a fake ID."""

    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        outputs = dict(args.inputs)
        # ConfigFile is a component resource; give it an empty output set.
        if args.typ == "kubernetes:yaml:ConfigFile":
            outputs = {}
        return [f"{args.name}-id", outputs]

    def call(self, args: pulumi.runtime.MockCallArgs):
        if args.token == "gcp:organizations/getProject:getProject":
            return {"number": "123456789", "projectId": args.args.get("projectId", "")}
        return {}


pulumi.runtime.set_mocks(MockGcp(), preview=False)
