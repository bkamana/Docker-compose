from __future__ import unicode_literals

import docker
import mock
from .. import unittest

from fig.container import Container
from fig.service import (
    Service,
    ServiceLink,
)
from fig.project import (
    ConfigurationError,
    NoSuchService,
    Project,
)


class ProjectTest(unittest.TestCase):
    def test_from_dict(self):
        project = Project.from_dicts('figtest', [
            {
                'name': 'web',
                'image': 'busybox:latest'
            },
            {
                'name': 'db',
                'image': 'busybox:latest'
            },
        ], None, None)
        self.assertEqual(len(project.services), 2)
        self.assertEqual(project.get_service('web').name, 'web')
        self.assertEqual(project.get_service('web').options['image'], 'busybox:latest')
        self.assertEqual(project.get_service('db').name, 'db')
        self.assertEqual(project.get_service('db').options['image'], 'busybox:latest')

    def test_from_dict_sorts_in_dependency_order(self):
        project = Project.from_dicts('figtest', [
            {
                'name': 'web',
                'image': 'busybox:latest',
                'links': ['db'],
            },
            {
                'name': 'db',
                'image': 'busybox:latest',
                'volumes_from': ['volume']
            },
            {
                'name': 'volume',
                'image': 'busybox:latest',
                'volumes': ['/tmp'],
            }
        ], None, None)

        self.assertEqual(project.services[0].name, 'volume')
        self.assertEqual(project.services[1].name, 'db')
        self.assertEqual(project.services[2].name, 'web')

    def test_from_config(self):
        project = Project.from_config('figtest', {
            'web': {
                'image': 'busybox:latest',
            },
            'db': {
                'image': 'busybox:latest',
            },
        }, None)
        self.assertEqual(len(project.services), 2)
        self.assertEqual(project.get_service('web').name, 'web')
        self.assertEqual(project.get_service('web').options['image'], 'busybox:latest')
        self.assertEqual(project.get_service('db').name, 'db')
        self.assertEqual(project.get_service('db').options['image'], 'busybox:latest')

    def test_from_config_throws_error_when_not_dict(self):
        with self.assertRaises(ConfigurationError):
            project = Project.from_config('figtest', {
                'web': 'busybox:latest',
            }, None)

    def test_up_with_fresh_start(self):
        mock_client = mock.create_autospec(docker.Client)
        services = [
            {'name': 'web', 'image': 'busybox:latest', 'links': ['db']},
            {'name': 'db',  'image': 'busybox:latest'},
        ]
        project = Project.from_dicts('test', services, mock_client, None)
        containers = project.up(do_build=False, fresh_start=True)
        self.assertEqual(len(containers), 2)

        def build_start_call(links):
            return mock.call.start(
                mock_client.create_container.return_value.__getitem__.return_value,
                links=links,
                cap_add=None,
                restart_policy=None,
                dns_search=None,
                network_mode='bridge',
                binds={},
                dns=None,
                volumes_from=[],
                port_bindings={},
                cap_drop=None,
                privileged=False,
            )

        expected = [
            mock.call.create_container(
                environment={},
                image='busybox:latest',
                detach=False,
                name='test_db_1',
            ),
            build_start_call([]),
            mock.call.create_container(
                environment={},
                image='busybox:latest',
                detach=False,
                name='test_web_1',
            ),
            build_start_call([
                ('test_db_1', 'db'),
                ('test_db_1', 'test_db_1'),
                ('test_db_1', 'db_1'),
            ]),
        ]
        self.assertEqual(mock_client.method_calls, expected)

    def test_get_service(self):
        web = Service(
            project='figtest',
            name='web',
            client=None,
            image="busybox:latest",
        )
        project = Project('test', [web], None, None)
        self.assertEqual(project.get_service('web'), web)

    def test_get_service_with_project_name(self):
        web = Service(project='figtest', name='web')
        project = Project('test', [web], None, None)
        self.assertEqual(project.get_service('test_web'), web)

    def test_get_service_not_found(self):
        project = Project('test', [], None, None)
        with self.assertRaises(NoSuchService):
            project.get_service('not_found')

    def test_get_services_returns_listed_services_with_args(self):
        web = Service(project='figtest', name='web')
        console = Service(project='figtest', name='console')
        project = Project('test', [web, console], None)
        self.assertEqual(project.get_services(['console']), [console])

    def test_get_services_with_include_links(self):
        db = Service(project='figtest', name='db')
        cache = Service( project='figtest', name='cache')
        web = Service(
            project='figtest',
            name='web',
            links=[ServiceLink(db, 'database')]
        )
        console = Service(
            project='figtest',
            name='console',
            links=[ServiceLink(web, 'web')]
        )
        project = Project('test', [web, db, cache, console], None)
        services = project.get_services(['console'], include_links=True)
        self.assertEqual(services, [db, web, console])

    def test_get_services_removes_duplicates_following_links(self):
        db = Service(project='figtest', name='db')
        web = Service(
            project='figtest',
            name='web',
            links=[ServiceLink(db, 'database')]
        )
        project = Project('test', [web, db], None)
        self.assertEqual(
            project.get_services(['web', 'db'], include_links=True),
            [db, web]
        )

    def test_get_links(self):
        db = Service(project='test', name='db')
        other = Service(project='test', name='other')
        project = Project('test', [db, other], None)
        config_links = [
            'db',
            'db:alias',
            'other',
        ]
        links = project.get_links(config_links, 'test')
        expected = [
            ServiceLink(db, None),
            ServiceLink(db, 'alias'),
            ServiceLink(other, None),
        ]
        self.assertEqual(links, expected)

    def test_get_links_no_links(self):
        project = Project('test', [], None)
        self.assertEqual(project.get_links(None, None), [])
