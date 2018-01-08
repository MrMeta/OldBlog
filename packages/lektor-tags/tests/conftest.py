import os
import pytest
import shutil
import tempfile


@pytest.fixture(scope='function')
def project():
    from lektor.project import Project
    return Project.from_path(os.path.join(os.path.dirname(__file__),
                                          'demo-project'))


@pytest.fixture(scope='function')
def env(project):
    from lektor.environment import Environment
    return Environment(project)


@pytest.fixture(scope='function')
def pad(env):
    from lektor.db import Database
    return Database(env).new_pad()


@pytest.fixture(scope='function')
def builder(tmpdir, pad):
    from lektor.builder import Builder
    return Builder(pad, str(tmpdir.mkdir("output")))


@pytest.fixture(scope='function')
def webui(request, env):
    from lektor.admin.webui import WebUI
    output_path = tempfile.mkdtemp()

    def cleanup():
        try:
            shutil.rmtree(output_path)
        except (OSError, IOError):
            pass
    request.addfinalizer(cleanup)

    return WebUI(env, output_path=output_path)
