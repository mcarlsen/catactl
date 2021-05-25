def test_env_app_root_exists(env):
    assert env.app_root.is_dir()
