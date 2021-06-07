import io
import tarfile
from typing import IO, List

from requests.auth import AuthBase


class DominoAPIKeyAuth(AuthBase):
    """Attaches Domino API Key Header to the given Request object."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def __eq__(self, other):
        return self.api_key == getattr(other, "api_key", None)

    def __ne__(self, other):
        return not self == other

    def __call__(self, r):
        r.headers["X-Domino-Api-Key"] = self.api_key
        return r


def list_to_string(val, separator="\n"):
    if isinstance(val, list):
        return separator.join(val)
    return val


def parse_plain_text(file_obj, encoding="utf-8") -> List[str]:
    lines = []
    if isinstance(file_obj, io.BufferedReader):
        file_content = file_obj.read().decode(encoding)
        lines = file_content.splitlines()
    return lines


def parse_dockerfile(file_obj) -> dict:
    content = dict()
    if isinstance(file_obj, io.BufferedReader):
        lines = parse_plain_text(file_obj)
        content["base_image"] = lines[0].strip("FROM ")
        content["instructions"] = lines[2:-2]  # Cut out the Domino specific instructions
    return content


REVISION_PARSERS = {
    "Dockerfile": parse_dockerfile,
    "preSetupScript.sh": parse_plain_text,
    "postSetupScript.sh": parse_plain_text,
    "preRunScript.sh": parse_plain_text,
    "postRunScript.sh": parse_plain_text,
}


def parse_revision_tar(file_obj: IO[bytes]) -> dict:
    content = dict()
    tar = tarfile.open(fileobj=file_obj)
    for member in tar.getmembers():
        file_name = member.name.split("/")[-1]
        parse_func = REVISION_PARSERS.get(file_name)
        if parse_func:
            extracted_file = tar.extractfile(member.name)
            content[file_name] = parse_func(extracted_file)

    return content
