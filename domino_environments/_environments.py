import io
import logging
import os
from typing import List

from domino.bearer_auth import BearerAuth
from domino.constants import DOMINO_LOG_LEVEL_KEY_NAME
from domino.helpers import (
    clean_host_url,
    get_api_key,
    get_host_or_throw_exception,
    get_path_to_domino_token_file,
    is_version_compatible,
)
from domino.http_request_manager import _HttpRequestManager
from requests.auth import HTTPBasicAuth

from ._version import __version__
from .utils import DominoAPIKeyAuth, parse_revision_tar


class ImageType:
    custom = "CustomImage"
    default = "DefaultImage"
    environment = "Environment"


class ClusterType:
    spark = "Spark"


class Visibility:
    global_ = "Global"
    organization = "Organization"
    private = "Private"


class _EnvironmentRoutes:
    def __init__(self, host: str):
        self.host = host

    def deployment_version(self):
        return self.host + "/version"

    def _build_environments_url(self) -> str:
        return self.host + "/v4/environments"

    def environment_default_get(self):
        return self._build_environments_url() + "/defaultEnvironment"

    def environment_create(self):
        return self.host + "/environments"

    def environment_get(self, environment_id):
        return self._build_environments_url() + f"/{environment_id}"

    def environment_remove(self, environment_id):
        return self._build_environments_url() + f"/{environment_id}/archive"

    def revision_create(self, environment_id):
        return self.host + f"/environments/{environment_id}/revisions"

    def revision_download(self, environment_id, revision_id):
        return (
            self.host
            + f"/v1/environments/{environment_id}/revisions/{revision_id}/dockerImageSourceProjectWeb"
        )


class Environment:
    def __init__(self, data: dict):
        self._data = data

    @property
    def id(self) -> str:
        return self._data.get("id")

    @property
    def latest_revision(self) -> dict:
        return self._data.get("latestRevision")

    @property
    def active_revision(self) -> dict:
        return self._data.get("selectedRevision")

    @property
    def archived(self) -> bool:
        return self._data.get("archived")

    @property
    def name(self) -> str:
        return self._data.get("name")

    @property
    def visibility(self) -> str:
        return self._data.get("visibility")

    @property
    def owner(self) -> dict:
        return self._data.get("owner")

    @property
    def supported_clusters(self) -> list:
        return self._data.get("supportedClusters")


class EnvironmentManager:
    _default_environment: Environment
    _default_environment_details: dict

    def __init__(self, base_url: str, api_key=None, domino_token_file=None):
        self._configure_logging()

        base_url: str = clean_host_url(get_host_or_throw_exception(base_url))
        domino_token_file = get_path_to_domino_token_file(domino_token_file)
        api_key: str = get_api_key(api_key)

        self.request_manager = self._initialise_request_manager(api_key, domino_token_file)
        self._routes = _EnvironmentRoutes(base_url)

        # Get Domino deployment version
        self._version = self.deployment_version()
        self.log.info(f"Domino deployment {base_url} is running version {self._version}")

        # Check version compatibility
        if not is_version_compatible(self._version):
            error_message = (
                f"Domino version: {self._version} is not compatible with "
                f"python-domino-environments version: {__version__}"
            )
            self.log.error(error_message)
            raise Exception(error_message)

        self.refresh_defaults()

    @property
    def log(self):
        try:
            return self._logger
        except AttributeError:
            self._configure_logging()
            return self._logger

    def _configure_logging(self):
        logging_level = logging.getLevelName(os.getenv(DOMINO_LOG_LEVEL_KEY_NAME, "INFO").upper())
        logging.basicConfig(level=logging_level)
        self._logger = logging.getLogger(__name__)

    def _initialise_request_manager(self, api_key: str, domino_token_file: str):
        if api_key is None and domino_token_file is None:
            raise Exception(
                "Either api_key or path_to_domino_token_file "
                "must be provided via class constructor or environment variable"
            )
        elif domino_token_file is not None:
            self.log.info(
                "Initializing python-domino-environments with bearer token auth"
            )
            return _HttpRequestManager(BearerAuth(domino_token_file))
        else:
            self.log.info(
                "Fallback: Initializing python-domino-environments with API key auth"
            )
            return _HttpRequestManager(DominoAPIKeyAuth(api_key))

    def deployment_version(self):
        url = self._routes.deployment_version()
        return self.request_manager.get(url).json().get("version")

    def refresh_defaults(self):
        self._default_environment = self.get_default_environment()
        self._default_environment_details = self.get_revision_details(self._default_environment)

    def get_default_environment(self) -> Environment:
        url = self._routes.environment_default_get()
        data = self.request_manager.get(url).json()
        return Environment(data)

    def archive_environment(self, environment: Environment):
        url = self._routes.environment_remove(environment.id)
        return self.request_manager.post(url)

    def get_environment(self, environment_id: str) -> Environment:
        url = self._routes.environment_get(environment_id)
        data = self.request_manager.get(url).json()
        return Environment(data)

    def create_environment(
        self,
        name: str,
        image_type: str,
        visibility: str,
        description: str = "",
        docker_image: str = "",
        base_environment_revision_id: str = None,
        base_default_environment_image: str = None,
        user_owner_id: str = None,
        organization_owner_id: str = None,
        cluster_types: str = None,
    ):
        if not base_environment_revision_id:
            base_environment_revision_id = self._default_environment.active_revision["id"]

        if not base_default_environment_image:
            base_default_environment_image = self._default_environment_details["Dockerfile"][
                "base_image"
            ]

        form_payload = {
            "name": name,
            "description": description,
            "visibility": visibility,
            "base.imageType": image_type,
            "base.dockerImage": docker_image,
            "base.baseEnvironmentRevisionId": base_environment_revision_id,
            "base.defaultEnvironmentImage": base_default_environment_image,
        }

        if visibility == Visibility.organization:
            form_payload["organizationOwnerId"] = organization_owner_id

        if user_owner_id:
            form_payload["userOwnerId"] = user_owner_id

        if cluster_types:
            form_payload["clusterTypes[]"] = cluster_types

        return self.request_manager.post(
            url=self._routes.environment_create(),
            data=form_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def get_revision_details(self, environment: Environment, revision_id: str = None) -> dict:
        """Gather Dockerfile instructions, Pre/Post Setup Script, and Pre/Post Run Script info.

        Args:
            environment: The environment object.
            revision_id: The ID of the revision, defaults to the environment's active revision.
        """
        revision_id = revision_id or environment.active_revision.get("id")
        return self._scrape_revision(environment.id, revision_id)

    def create_revision(
        self,
        environment: Environment,
        image_type: str,
        docker_image: str = "",
        base_environment_revision_id: str = None,
        base_default_environment_image: str = None,
        dockerfile_instructions: str = "",
        workspace_tools: str = "",
        pre_run_script: str = "",
        post_run_script: str = "",
        pre_setup_script: str = "",
        post_setup_script: str = "",
        environment_variables: List[tuple] = None,
        force_rebuild: bool = False,
        should_use_vpn: bool = False,
        cluster_types: str = None,
        docker_arguments: str = "",
        summary: str = "",
    ):
        if not base_environment_revision_id:
            base_environment_revision_id = self._default_environment.active_revision["id"]

        if not base_default_environment_image:
            base_default_environment_image = self._default_environment_details["Dockerfile"][
                "base_image"
            ]

        form_payload = {
            "base.imageType": image_type,
            "base.dockerImage": docker_image,
            "base.baseEnvironmentRevisionId": base_environment_revision_id,
            "base.defaultEnvironmentImage": base_default_environment_image,
            "dockerfileInstructions": dockerfile_instructions,
            "properties": workspace_tools,
            "preRunScript": pre_run_script,
            "postRunScript": post_run_script,
            "preSetupScript": pre_setup_script,
            "postSetupScript": post_setup_script,
            "dockerArguments": docker_arguments,
            "summary": summary,
        }

        if environment_variables:
            for idx, env_var in enumerate(environment_variables):
                form_payload[f"buildEnvironmentVariables[{idx}].name"] = env_var[0]
                form_payload[f"buildEnvironmentVariables[{idx}].value"] = env_var[1]

        if force_rebuild:
            form_payload["noCache"] = True

        if should_use_vpn:
            form_payload["shouldUseVPN"] = "on"

        if cluster_types:
            form_payload["clusterTypes[]"] = cluster_types

        return self.request_manager.post(
            url=self._routes.revision_create(environment.id),
            data=form_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def _scrape_revision(self, environment_id: str, revision_id: str) -> dict:
        url = self._routes.revision_download(environment_id, revision_id)
        res = self.request_manager.get(url)
        file_io = io.BytesIO(res.content)
        return parse_revision_tar(file_io)
