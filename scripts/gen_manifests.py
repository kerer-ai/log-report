#!/usr/bin/env python3
"""Generate all manifests from PR comment data."""
import json, os

manifests = {
    "pytorch": {
        "repo": "Ascend/pytorch", "pr": 39391, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_pytorch", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T15:45:00+08:00",
        "tasks": [
            {"task_name": "Build_X86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=c4971988a9ea47e896c0940d5cdc27cb&stepRunId=411d0ed09d3143c6b799f52bd7bfe626&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=3fdd086c799a443bb9cff06d960bd65c&stepRunId=1512c8de029d45858df0813e9380d243&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_LibTorch_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=3a5ca95ac9f44ad28b996044e6e0f85c&stepRunId=85aaf9056d884fc0ba47c3b24cbb1b39&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_LibTorch_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=f13beacd44824e3fab029bbb0dd7f21a&stepRunId=20706748fba44b8a82695b43e15e60aa&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_X86_torchair", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=371924a86f3f4a3ebec43e8bb6444ac4&stepRunId=8383886198064e38bdf087e1cd7bc4a8&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_ARM_torchair", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=4d0b1fc91a844300bb9e0c620ca70bfd&stepRunId=3eac7a86cf3c4db0b6e1322874746ba5&codeHostingPlatformFlag=gitcode"},
            {"task_name": "patch_test", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=9ab4a8ad25bd4afeb808647efc5fc2f1&pipelineRunId=62c26e9e50624164a28df9cdd8aa3cf7&stepId=ec47f39e78fa49668b5c945cd0df7449&jobRunId=a10b41bf6f874cabb0ac323e65dd9cfe&stepRunId=b56eed2ea62e4e01a829166ff827bdad&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "torchair": {
        "repo": "Ascend/torchair", "pr": 3253, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_torchair", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=4584af00613748b5854a22a4603c0155&pipelineRunId=c840539a735d46a4a63989b3eeaa550d&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-24T17:30:00+08:00",
        "tasks": [
            {"task_name": "Build_x86", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=4584af00613748b5854a22a4603c0155&pipelineRunId=c840539a735d46a4a63989b3eeaa550d&stepId=1f264454a0da4a4a8aa5dd7c1c2ddece&jobRunId=216a5d42e3964462829a4b8acfd935a4&stepRunId=d7213078156c4933b6df1f5f16c063cd&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_ARM", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=4584af00613748b5854a22a4603c0155&pipelineRunId=c840539a735d46a4a63989b3eeaa550d&stepId=1f264454a0da4a4a8aa5dd7c1c2ddece&jobRunId=d9bfd1beaa2149c4a74f7d6fcf2afa64&stepRunId=7d906da9b4b14293a2bff836a32587ed&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "MindIE-LLM": {
        "repo": "Ascend/MindIE-LLM", "pr": 1077, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_MindIE-LLM_gitcode", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-25T11:28:00+08:00",
        "tasks": [
            {"task_name": "Build_ops_x86_A3", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1fafa7ecec7f48b185581736faaeb3b3&jobRunId=ce13fffd13834d89a6797a2b0cdcafdc&stepRunId=98700e18ec1f43f0b38c352ea4c088d5&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_ops_arm_A3", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1fafa7ecec7f48b185581736faaeb3b3&jobRunId=ee03de9929be4cd98cce5506a65f1d5b&stepRunId=d467ed1f627841efa82959b059c638b6&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_ops_x86_A2", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1fafa7ecec7f48b185581736faaeb3b3&jobRunId=acd1354f6c8e45a4b923e968db61047a&stepRunId=430fbca6fc7e40af882ae899917c072c&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_ops_arm_A2", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1fafa7ecec7f48b185581736faaeb3b3&jobRunId=25b7bd2bf4f241678239e1c0aab4a93d&stepRunId=99762087ef7a4926a93c6340a9eca51d&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_x86_abi1_atb", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1afcdb5862594e1086b2d89dae881832&jobRunId=eea538987f6a4f2eb120fe6ac228f315&stepRunId=914d28ad28724f19abeb0cc3bf8bc6f2&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_x86_abi1_llm", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1afcdb5862594e1086b2d89dae881832&jobRunId=3b579345e6fd40f9992c3315ccc95265&stepRunId=9060992092cf42a28fb65974b112f8ad&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_arm_abi1_atb", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1afcdb5862594e1086b2d89dae881832&jobRunId=9a6a8443194a46e4a4d398adf080a7a8&stepRunId=d9db917d9ad94ddcbd7d28365f8c2cb0&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_arm_abi1_llm", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1afcdb5862594e1086b2d89dae881832&jobRunId=b8e15ba30db64080819951c358c05f2d&stepRunId=5f6b7343ec26426abd9584246899aaaa&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_arm_abi0_atb", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1afcdb5862594e1086b2d89dae881832&jobRunId=6e9bf6f73ea646ea841f3e557b561b80&stepRunId=eff822f77d664334b9f49929e3fe0720&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_arm_abi0_llm", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=9c5f15c87df447d38e536dcb082b7c04&pipelineRunId=667c691cfabc45d68b89bd6c8f6c7f8c&stepId=1afcdb5862594e1086b2d89dae881832&jobRunId=fc647317cdd1442d806a73e4a210b3f8&stepRunId=8d2acfc8e51d4d4c8009557950d63319&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "MindIE-SD": {
        "repo": "Ascend/MindIE-SD", "pr": 380, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_MindIE-SD_gitcode", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=1fb7edac5d0b4cf095f25ebea7376e75&pipelineRunId=2a1a78a244c44486a62b90a334792f0b&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-24T22:48:00+08:00",
        "tasks": [
            {"task_name": "Build_linux_x86_abi1", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=1fb7edac5d0b4cf095f25ebea7376e75&pipelineRunId=2a1a78a244c44486a62b90a334792f0b&stepId=95a6427e514240a5800644368b0d9653&jobRunId=200c1b0f8b22428daa2282ce7fc668f6&stepRunId=a188bfb0b89a4c83b74dc3ac717454c7&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_arm_abi1", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=1fb7edac5d0b4cf095f25ebea7376e75&pipelineRunId=2a1a78a244c44486a62b90a334792f0b&stepId=95a6427e514240a5800644368b0d9653&jobRunId=e1000500092243b6a2c304c837195da1&stepRunId=e950cf61e14e46fcb68c51f960f37bf6&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_linux_arm_abi0", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=1fb7edac5d0b4cf095f25ebea7376e75&pipelineRunId=2a1a78a244c44486a62b90a334792f0b&stepId=95a6427e514240a5800644368b0d9653&jobRunId=2724680c83294987b88b88e719084da6&stepRunId=e5a8ddeadb1143d2ac6be1c09c4c4e37&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "MindIE-PyMotor": {
        "repo": "Ascend/MindIE-PyMotor", "pr": 351, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_MindIE-pyMotor_gitcode", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=54a49e4bca684766afd90648e71ee6dd&pipelineRunId=34aa970006ea47b49ce988c4d60ae4f8&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-25T20:55:00+08:00",
        "tasks": [
            {"task_name": "Build_linux_arm", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300036&pipelineId=54a49e4bca684766afd90648e71ee6dd&pipelineRunId=34aa970006ea47b49ce988c4d60ae4f8&stepId=c61cf69f726d4aab8bb8b782aef8a158&jobRunId=26732204f13c44a9ae73fc6f66b8543d&stepRunId=cce26939c01c40e4a0eff00d327f872b&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "MindSpeed": {
        "repo": "Ascend/MindSpeed", "pr": 3574, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_MindSpeed", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300091&pipelineId=baddd3989ead4da4a892aec23193542c&pipelineRunId=ac1a01c78e974130802ff0bfff77c83c&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T09:38:00+08:00",
        "tasks": [
            {"task_name": "Build", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300091&pipelineId=baddd3989ead4da4a892aec23193542c&pipelineRunId=ac1a01c78e974130802ff0bfff77c83c&stepId=5fb65047ab8042d898f739e868986891&jobRunId=73ebfaf9e49a43e3b606d6f10fd98fb7&stepRunId=3b738e07d781453f9a209d6d00ba3d41&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "MindSpeed-MM": {
        "repo": "Ascend/MindSpeed-MM", "pr": 2720, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_MindSpeed-MM", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300091&pipelineId=77de0fe131d3441086e8c8f2427b1638&pipelineRunId=235dd4f0aa2649dd9ff50c6308b18d20&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-25T16:32:00+08:00",
        "tasks": [
            {"task_name": "Build", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300091&pipelineId=77de0fe131d3441086e8c8f2427b1638&pipelineRunId=235dd4f0aa2649dd9ff50c6308b18d20&stepId=6d809103cbe24abba2f3bbeab02d2531&jobRunId=87d47601cb6b4c45902463b1ad3ca8ac&stepRunId=6966bae17ca44c4fa1ccb33471aa858c&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "op-plugin": {
        "repo": "Ascend/op-plugin", "pr": 5283, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_op-plugin", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T15:26:00+08:00",
        "tasks": [
            {"task_name": "Build_master_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=f0abcd0055ac478dab4f37f6b4227795&stepRunId=5b0fd989f96c472d98900778cd452336&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_7_1_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=dcfcd2b448ed45608fe70c5562d9da9e&stepRunId=eb9940097f3845ebaa8697c90c8486ff&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_9_0_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=a95e26685df64a2d9fbd3cb018d761c5&stepRunId=f1d71de240ac44f3929d3d8de4aa960c&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_10_0_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=08f3d5f88e2e481c92f1ceb91eec84bf&stepRunId=feee3fee929d4ec5b67b7c3b2505c13b&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_11_0_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=c3e4f7e1fd8f4e83866898d7c6a6f4d6&stepRunId=77171612ce124effbf663150d1414d80&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_12_0_ARM", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=3e78ac0beb674b4f83a4b7db7e27e432&stepRunId=f70fee30ce6e4e739952be01dc72662d&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_master_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=775d4574ec9b4747b14f589367444dc6&stepRunId=853f3b1826864bf895525004c112e173&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_7_1_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=8d8bfd383ceb4c7a957d58868ef4f7b6&stepRunId=45bc1cd860704ba19b48fff2616a0ba7&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_9_0_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=9385f62abf664fe581b03f2387ad09bf&stepRunId=c583b6403c9841c788e113cc73ba574d&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_10_0_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=fafad40d1ed743c2bbbaa142a814731a&stepRunId=a04ec449c4b64d3580592d3a9c383d6f&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_11_0_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=8a763ad665ef406c97b59f69448a3503&stepRunId=64034c78d6554dcdbf0cd92539745c97&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_v2_12_0_x86", "status": "failed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=4&pipelineId=f2201d0732ac41cb84bf537b9708d2df&pipelineRunId=af3399082923477da09eedc9c08fc6a4&stepId=734a9532a1954b82937cd8a91f369e47&jobRunId=c4e8d495a9484446b54679c9a81f76fa&stepRunId=d3ec647bb6e54c6fa8d75a08aa1b62bf&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "hmpi": {
        "repo": "kunpengcompute/hmpi", "pr": 91, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_hmpi", "pipeline_state": "failed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=9afc534b0f9e418dacc45164126841f2&pipelineRunId=ec87c48bf9e4438e90e4277692f8b376&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T14:50:00+08:00",
        "tasks": [
            {"task_name": "Build_gcc", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=9afc534b0f9e418dacc45164126841f2&pipelineRunId=ec87c48bf9e4438e90e4277692f8b376&stepId=e092fbe52ba84d51ad77a7102b4971bf&jobRunId=da5b744d441140329ad7839f2516d7c2&stepRunId=e40618abca704056908b925939b9b017&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_bisheng", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=9afc534b0f9e418dacc45164126841f2&pipelineRunId=ec87c48bf9e4438e90e4277692f8b376&stepId=e092fbe52ba84d51ad77a7102b4971bf&jobRunId=48ee64c3709a4abc985ca81953fc8f79&stepRunId=09d9374aacab4d81ba9c94ec387bddad&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "hucx": {
        "repo": "kunpengcompute/hucx", "pr": 49, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_hucx", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=2e418ed0c2e440fd9ffad8083e4bd0a7&pipelineRunId=35d2348fee4e406fa17d8ba0e70ddf49&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-25T17:00:00+08:00",
        "tasks": [
            {"task_name": "Build_gcc", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=2e418ed0c2e440fd9ffad8083e4bd0a7&pipelineRunId=35d2348fee4e406fa17d8ba0e70ddf49&stepId=edd0149104d54e70ab3a67acee3c4e8d&jobRunId=1003bf68cba945bd8a29da32edf82d1d&stepRunId=dc3b1cb0ce4d483bb69930ca91dc7e63&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_bisheng", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=2e418ed0c2e440fd9ffad8083e4bd0a7&pipelineRunId=35d2348fee4e406fa17d8ba0e70ddf49&stepId=edd0149104d54e70ab3a67acee3c4e8d&jobRunId=95e0259ca26648ffa57f10a5929d2a4c&stepRunId=374b73ceda9b48588d3d14b62a321977&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "xucg": {
        "repo": "kunpengcompute/xucg", "pr": 69, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_xucg", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=deca5186541949aaa14ef44b6874a886&pipelineRunId=c379978f555642e69282f197f195acf2&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T14:50:00+08:00",
        "tasks": [
            {"task_name": "Build_gcc", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=deca5186541949aaa14ef44b6874a886&pipelineRunId=c379978f555642e69282f197f195acf2&stepId=0888f311045e428c98543f7cc48dc7db&jobRunId=9f982759dc7642ef82d8c5d735dea313&stepRunId=21dc49c55c8e4408814393636336212d&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_bisheng", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300073&pipelineId=deca5186541949aaa14ef44b6874a886&pipelineRunId=c379978f555642e69282f197f195acf2&stepId=0888f311045e428c98543f7cc48dc7db&jobRunId=380466936e004622ad5e67ee592eb2cf&stepRunId=e943c4eac8754c25bb50b01e84758f8c&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "kernel": {
        "repo": "openeuler/kernel", "pr": 24242, "ci_backend": "jenkins",
        "pipeline_name": "openeuler kernel check_build (multiarch)", "pipeline_state": "passed",
        "pipeline_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/trigger/job/kernel/10057/console",
        "comment_time": "2026-06-26T13:05:00+08:00",
        "tasks": [
            {"task_name": "aarch64_check_build", "status": "passed", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/aarch64/job/kernel/9995/console"},
            {"task_name": "x86_64_check_build", "status": "passed", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/x86-64/job/kernel/9993/console"},
            {"task_name": "ppc_check_build", "status": "passed", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/ppc/job/kernel/10010/console"},
            {"task_name": "ppc64_check_build", "status": "passed", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/ppc64/job/kernel/10014/console"},
            {"task_name": "loongarch_check_build", "status": "passed", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/loongarch/job/kernel/10025/console"},
            {"task_name": "arm_check_build", "status": "passed", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/arm/job/kernel/10026/console"},
            {"task_name": "riscv64_check_build", "status": "warning", "detail_url": "https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler/job/riscv64/job/kernel/10025/console"},
        ]
    },
    "memfabric_hybrid": {
        "repo": "Ascend/memfabric_hybrid", "pr": 883, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_memfabric_hybrid", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300066&pipelineId=87d48bd7790b4cf7adeca978bdf2ce52&pipelineRunId=a2be9c02c68c4d42875b346759ed0d4f&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T08:00:00+08:00",
        "tasks": [
            {"task_name": "Build_memfabric-hybrid", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300066&pipelineId=87d48bd7790b4cf7adeca978bdf2ce52&pipelineRunId=a2be9c02c68c4d42875b346759ed0d4f&stepId=bb235c3b42194a41a7dae6c36805cae2&jobRunId=75fead4ee431461cb8b2ae9377b35bcc&stepRunId=5ca8ee12345e496fa767bb65997a2cae&codeHostingPlatformFlag=gitcode"},
            {"task_name": "Build_memfabric-hybrid-bazel", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300066&pipelineId=87d48bd7790b4cf7adeca978bdf2ce52&pipelineRunId=a2be9c02c68c4d42875b346759ed0d4f&stepId=bb235c3b42194a41a7dae6c36805cae2&jobRunId=813eb87f681241c9b1c05215de1a9247&stepRunId=ed534c875de74bc887db10681a6236cf&codeHostingPlatformFlag=gitcode"},
        ]
    },
    "memcache": {
        "repo": "Ascend/memcache", "pr": 327, "ci_backend": "openlibing",
        "pipeline_name": "PR-pipeline_memcache", "pipeline_state": "passed",
        "pipeline_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300066&pipelineId=d33796067f29467b9e00cc14ffcd86eb&pipelineRunId=e223e63460c44c4b9ddf418a13e3f518&codeHostingPlatformFlag=gitcode",
        "comment_time": "2026-06-26T08:00:00+08:00",
        "tasks": [
            {"task_name": "Build_memcache", "status": "passed", "detail_url": "https://www.openlibing.com/apps/pipelineDetail?projectId=300066&pipelineId=d33796067f29467b9e00cc14ffcd86eb&pipelineRunId=e223e63460c44c4b9ddf418a13e3f518&stepId=0670c86ca83f4a76a4f0cd3a08dd5cc1&jobRunId=fa0dc1ffcc62439b8a8db5e086b0614b&stepRunId=4f1bfa47229e445e831d7eaa3802fe1d&codeHostingPlatformFlag=gitcode"},
        ]
    },
}

os.makedirs("json-org", exist_ok=True)
for name, m in manifests.items():
    manifest = {
        "repo": m["repo"],
        "pr": m["pr"],
        "pr_url": f"https://gitcode.com/{m['repo']}/pull/{m['pr']}",
        "ci_backend": m["ci_backend"],
        "pipeline_name": m["pipeline_name"],
        "pipeline_state": m["pipeline_state"],
        "pipeline_url": m["pipeline_url"],
        "comment_time": m["comment_time"],
        "tasks": m["tasks"],
    }
    path = f"json-org/{name}_manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Created {path}: {len(m['tasks'])} tasks")
