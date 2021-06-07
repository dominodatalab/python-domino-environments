# python-domino-environments

## Installation

Install with `pip`
```shell
pip install git+https://github.com/dominodatalab/python-domino-environments.git
```

## Usage

Importing the library
```python
# Both import statements are equivalent
from domino_environments import *
from domino_environments import Environment, EnvironmentManager, ImageType, ClusterType, Visibility
```

Setup the connection to Domino
```python
# Instantiate a new environment manager object
env_man = EnvironmentManager(host="https://field.cs.domino.tech", api_key="8ed02...")

# You can also pass the host and API key through environment variables
# host          -> DOMINO_API_HOST
# api_key       -> DOMINO_USER_API_KEY
# token_file    -> DOMINO_TOKEN_FILE
env_man = EnvironmentManager()
```

Working with environments

```python
# Retrieves the default environment
default_env = env_man.get_default_environment()

# Retrieve an environment by ID
target_env = env_man.get_environment("60709c5c110dac3d9bab6485")

# Archive an environment by ID
env_man.archive_environment(target_env)

# Create a private environment using a custom base image
env_man.create_environment(
    name="Ubuntu 18 - DAD Py3.6 R3.6",
    image_type=ImageType.CUSTOM,
    visibility=Visibility.PRIVATE,
    description=[
        "Domino Analytics Distribution",
        "Ubuntu 18.04 - Python 3.6 - R 3.6",
        "2020-05-08"
    ],
    docker_image="quay.io/domino/base:Ubuntu18_DAD_Py3.6_R3.6_20200508",
    user_owner_id="607dc22f3d5afefc9f81b599",  # Optional, defaults to current user
)

# Create a global environment using the default base image
env_man.create_environment(
    name="Base Env",
    image_type=ImageType.DEFAULT,
    visibility=Visibility.GLOBAL,
    description="Contains all the packages and tools in use by all users.",
)

# Create an organization environment using another environment as the base
env_man.create_environment(
    name="Team 1 - Packages & Tools",
    image_type=ImageType.ENVIRONMENT,
    visibility=Visibility.ORGANIZATION,
    description="Contains all the packages and tools in use by Team 1 members.",
    base_environment_revision_id="60709c5c110dac3d9bab6486",
    organization_owner_id="609c0da3140b065c849b84ab",
)

# Create a global environment for use as a Spark node
env_man.create_environment(
    name="Spark 2.4.6",
    image_type=ImageType.CUSTOM,
    visibility=Visibility.GLOBAL,
    description="Env 1 description.",
    docker_image="bitnami/spark:2.4.6",
    cluster_types=ClusterType.SPARK,
)
```

Working with environment revisions
```python
# You need an environment object to work with it's revisions
env = env_man.get_environment("60709c5c110dac3d9bab6485")

# Retrieve the active revision (most recent successful build)
print(env.active_revision)

# Retrieve the latest revision (most recent build, regardless of success)
print(env.latest_revision)

# Retrieve the details of a revision (includes Dockerfile instructions and pre/post run/setup scripts)
rev_details = env_man.get_revision_details(environment=env, revision_id=env.active_revision["id"])

# If only an environment is passed, then the active revision will be used (equivalent to above statement)
rev_details = env_man.get_revision_details(env)

# Create a new revision
env_man.create_revision(
    environment=env,
    image_type=ImageType.CUSTOM,
    docker_image="quay.io/domino/base:Ubuntu18_DAD_Py3.6_R3.6_20200508",
    
    # Pass a string or list of strings for Dockerfile instructions, workspace tools,
    # pre/post run/setup scripts, and docker arguments
    dockerfile_instructions=[
        "RUN apt-get update && apt-get install -y wget unzip",
        "",
        "RUN echo test && \\",
        "    echo test2",
    ],
    workspace_tools=[
        "vscode:"
        "  title: \"vscode\""
        "  iconUrl: \"/assets/images/workspace-logos/vscode.svg\""
        "  start: [ \"/var/opt/workspaces/vscode/start\" ]"
        "  httpProxy:"
        "    port: 8888"
        "    requireSubdomain: false"
    ],
    pre_run_script='echo "Pre Run Script"',
    post_run_script='echo "Post Run Script"',
    pre_setup_script='echo "Pre Setup Script"',
    post_setup_script='echo "Post Setup Script"',
    docker_arguments="--name testenv",
    
    # Either a dictionary or a list of tuples is accepted for environment variables
    environment_variables=[
        ("Key1", "Val1"),
        ("Key2", "Val2"),
    ],
    
    force_rebuild=True,     # Defaults to False
    should_use_vpn=True,    # Defaults to False
    cluster_types=ClusterType.SPARK,
    summary="This is a summary of the changes made during this revision.",
)
```
