import io
import logging
import os
import re
from typing import List, Union

# python-domino version compatibility
try:
    from domino.bearer_auth import BearerAuth
except:
    from domino.authentication import BearerAuth

from domino.constants import DOMINO_LOG_LEVEL_KEY_NAME, DOMINO_HOST_KEY_NAME, DOMINO_TOKEN_FILE_KEY_NAME, DOMINO_USER_API_KEY_KEY_NAME
from domino.helpers import (
    clean_host_url,
    is_version_compatible,
)
from domino.http_request_manager import _HttpRequestManager

from ._version import __version__
from .utils import DominoAPIKeyAuth, list_to_string, parse_revision_tar


class ImageType:
    CUSTOM = "CustomImage"
    DEFAULT = "DefaultImage"
    ENVIRONMENT = "Environment"


class ClusterType:
    SPARK = "Spark"
    RAY = "Ray"
    DASK = "Dask"


class Visibility:
    GLOBAL = "Global"
    ORGANIZATION = "Organization"
    PRIVATE = "Private"


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

    def revision_summaries(self, environment_id, pageStart, pageEnd):
        return (
            self.host
            + f"/environments/{environment_id}/json/paged/{pageStart}/{pageEnd}"
        )

    def build_logs(self, build_logs_url: str):
        return (
            self.host + build_logs_url.replace("/logs","/fetchBuildLogsSince")
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
    _default_details: dict

    def __init__(self, host=None, api_key=None, domino_token_file=None):
        """
        Args:
            host: (Optional) A host URL.
                If not provided the library will expect to find one in the
                DOMINO_API_HOST environment variable.
            api_key: (Optional) An API key to authenticate with.
                If not provided the library will expect to find one in the
                DOMINO_USER_API_KEY environment variable.
            domino_token_file: (Optional) Path to domino token file containing auth token.
                If not provided the library will expect to find one in the
                DOMINO_TOKEN_FILE environment variable.
        """
        self._configure_logging()

        _host = host or os.getenv(DOMINO_HOST_KEY_NAME)
        if not _host:
            error_message = f"Host must be supplied as a parameter or through the "
            f"{DOMINO_HOST_KEY_NAME} environment variable."
            self.log.error(error_message)
            raise Exception(error_message)

        host: str = clean_host_url(_host)
        domino_token_file = domino_token_file or os.getenv(DOMINO_TOKEN_FILE_KEY_NAME)
        api_key: str = api_key or os.getenv(DOMINO_USER_API_KEY_KEY_NAME)

        self.request_manager = self._initialise_request_manager(api_key, domino_token_file)
        self._routes = _EnvironmentRoutes(host)

        # Get Domino deployment version
        self._version = self.deployment_version()
        self.log.info(f"Domino deployment {host} is running version {self._version}")

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
            self.log.info("Initializing python-domino-environments with bearer token auth")
            return _HttpRequestManager(BearerAuth(domino_token_file))
        else:
            self.log.info("Fallback: Initializing python-domino-environments with API key auth")
            return _HttpRequestManager(DominoAPIKeyAuth(api_key))

    def deployment_version(self):
        url = self._routes.deployment_version()
        return self.request_manager.get(url).json().get("version")

    def refresh_defaults(self):
        self._default_environment = self.get_default_environment()
        self._default_details = self.get_revision_details(self._default_environment)

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
        description: Union[str, List[str]] = "",
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
            base_default_environment_image = self._default_details["Dockerfile"]["base_image"]

        # Ensure that the description is a string
        description = list_to_string(description)

        form_payload = {
            "name": name,
            "description": description,
            "visibility": visibility,
            "base.imageType": image_type,
            "base.dockerImage": docker_image,
            "base.baseEnvironmentRevisionId": base_environment_revision_id,
            "base.defaultEnvironmentImage": base_default_environment_image,
        }

        if visibility == Visibility.ORGANIZATION:
            form_payload["organizationOwnerId"] = organization_owner_id

        if user_owner_id:
            form_payload["userOwnerId"] = user_owner_id

        if cluster_types:
            form_payload["clusterTypes[]"] = cluster_types

        response = self.request_manager.post(
            url=self._routes.environment_create(),
            data=form_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.ok:
            env_id = response.url.split("/")[-1]
            if env_id == "environments":
                raise ValueError(f"Did not create the environment due to invalid configuration")
            return (response, env_id)
        else:
            # Should we maybe raise an exception here?
            response.raise_for_status()
            return (response, None)

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
        dockerfile_instructions: Union[str, List[str]] = "",
        workspace_tools: Union[str, List[str]] = "",
        pre_run_script: Union[str, List[str]] = "",
        post_run_script: Union[str, List[str]] = "",
        pre_setup_script: Union[str, List[str]] = "",
        post_setup_script: Union[str, List[str]] = "",
        environment_variables: Union[dict, List[tuple]] = None,
        docker_arguments: Union[str, List[str]] = "",
        force_rebuild: bool = False,
        should_use_vpn: bool = False,
        cluster_types: str = None,
        summary: str = "",
    ):
        if not base_environment_revision_id:
            base_environment_revision_id = self._default_environment.active_revision["id"]

        if not base_default_environment_image:
            base_default_environment_image = self._default_details["Dockerfile"]["base_image"]

        # Ensure that each variable is a single string
        dockerfile_instructions = list_to_string(dockerfile_instructions)
        workspace_tools = list_to_string(workspace_tools)
        pre_run_script = list_to_string(pre_run_script)
        post_run_script = list_to_string(post_run_script)
        pre_setup_script = list_to_string(pre_setup_script)
        post_setup_script = list_to_string(post_setup_script)
        docker_arguments = list_to_string(docker_arguments)

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
            if isinstance(environment_variables, dict):
                # Convert dictionary to a list of tuples
                environment_variables = list(environment_variables.items())

            for idx, (key, val) in enumerate(environment_variables):
                form_payload[f"buildEnvironmentVariables[{idx}].name"] = key
                form_payload[f"buildEnvironmentVariables[{idx}].value"] = val

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

    #TODO: add some paging logic in here. search 10/20 at a time and fail if not found
    def get_build_status(self, environment: Environment, revision_id: str = None):
        """Gather current status of build job for a given environment/revision

        Args:
            environment: The environment object.
            revision_id: The ID of the revision, defaults to the environment's latest revision.
        """
        revision_id = revision_id or environment.latest_revision.get("id")
        summary = self._get_revision_summary(environment.id)
        return summary['buildStatus'][revision_id]

    def get_build_logs(self, environment: Environment, revision_id: str = None):
        """Gather logs of build job for a given environment/revision

        Args:
            environment: The environment object.
            revision_id: The ID of the revision, defaults to the environment's latest revision.
        """
        revision_id = revision_id or environment.latest_revision.get("id")
        summary = self._get_revision_summary(environment.id)
        logs_url = summary['buildLogsUrl'][revision_id]

        url = self._routes.build_logs(logs_url)
        res = self.request_manager.get(url)

        regex = re.compile((r'<td class="line".*?>(.*)</td>'))
        logs_matching = regex.findall(res.text)

        return logs_matching



    def _scrape_revision(self, environment_id: str, revision_id: str) -> dict:
        url = self._routes.revision_download(environment_id, revision_id)
        res = self.request_manager.get(url)
        file_io = io.BytesIO(res.content)
        return parse_revision_tar(file_io)


    def _get_revision_summary(self, environment_id: str, pageStart=0, pageEnd=500) -> dict:
        url = self._routes.revision_summaries(environment_id, pageStart, pageEnd)
        res = self.request_manager.get(url)
        return res.json()
