from importlib.metadata import version


def test_package_imports_with_matching_distribution_version() -> None:
    import harness

    assert harness.__version__ == version("da-harness-agent")
