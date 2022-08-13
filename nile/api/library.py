from nile import constants
from nile.proto import sds_proto2_pb2
import logging
import uuid
import os
import json
import hashlib


class Library:
    def __init__(self, config_manager, session_manager):
        self.config = config_manager
        self.session_manager = session_manager
        self.logger = logging.getLogger("LIBRARY")

    def request_sds(self, target, token, body):
        headers = {
            "X-Amz-Target": target,
            "x-amzn-token": token,
            "User-Agent": "com.amazon.agslauncher.win/2.1.7437.6",
            "UserAgent": "com.amazon.agslauncher.win/2.1.7437.6",
            "Content-Type": "application/json",
            "Content-Encoding": "amz-1.0",
        }
        response = self.session_manager.session.post(
            f"{constants.AMAZON_SDS}/amazon/",
            headers=headers,
            json=body,
        )

        return response

    def _get_sync_request_data(self, serial, nextToken=None):
        request_data = {
            "Operation": "GetEntitlementsV2",
            "clientId": "Sonic",
            "syncPoint": None,
            "nextToken": nextToken,
            "maxResults": 50,
            "productIdFilter": None,
            "keyId": "d5dc8b8b-86c8-4fc4-ae93-18c0def5314d",
            "hardwareHash": hashlib.sha256(serial.encode()).hexdigest().upper(),
        }

        return request_data

    def sync(self):
        self.logger.info("Synchronizing library")

        token, serial = self.config.get(
            "user",
            [
                "tokens//bearer//access_token",
                "extensions//device_info//device_serial_number",
            ],
        )
        games = list()
        nextToken = None
        while True:
            request_data = self._get_sync_request_data(serial, nextToken)

            response = self.request_sds(
                "com.amazonaws.gearbox.softwaredistribution.service.model.SoftwareDistributionService.GetEntitlementsV2",
                token,
                request_data,
            )
            json_data = response.json()
            games.extend(json_data["entitlements"])

            if not "nextToken" in json_data:
                break
            else:
                self.logger.info("Got next token in response, making next request")
                nextToken = json_data["nextToken"]

            if not response.ok:
                self.logger.error("There was an error syncing library")
                self.logger.debug(response.content)
                return
        # Remove duplicates
        games_dict = dict()
        for game in games:
            if not games_dict.get(game["product"]["id"]):
                games_dict[game["product"]["id"]] = game

        self.config.write("library", list(games_dict.values()))
        self.logger.info("Successfully synced the library")
        self.pull_games_tumbnails()

    def get_game_image_fs_path(self, id):
        return os.path.join(constants.CACHE_PATH, "images", id + ".jpg")

    def pull_games_tumbnails(self):
        games = self.config.get("library")
        if not games:
            return
        for game in games:
            file_path = self.get_game_image_fs_path(game["product"]["id"])
            directory, _ = os.path.split(file_path)
            if not os.path.exists(directory):
                os.makedirs(directory)
            if os.path.exists(file_path):
                continue
            url = game["product"]["productDetail"]["iconUrl"]
            data = self.fetch_thumbnail(url)
            if not data:
                data = self.fetch_thumbnail(url)

            if not data:
                continue

            file = open(file_path, "wb")
            file.write(data)
            file.flush()
            file.close()

    def fetch_thumbnail(self, url):
        response = self.session_manager.session.get(url)

        if response.ok:
            return response.content

    def get_game_manifest(self, id: str):
        token = self.config.get("user", "tokens//bearer//access_token")

        request_data = {
            "adgGoodId": id,
            "previousVersionId": None,
            "keyId": "d5dc8b8b-86c8-4fc4-ae93-18c0def5314d",
            "Operation": "GetDownloadManifestV3",
        }

        response = self.request_sds(
            "com.amazonaws.gearbox.softwaredistribution.service.model.SoftwareDistributionService.GetDownloadManifestV3",
            token,
            request_data,
        )

        if not response.ok:
            self.logger.error("There was an error getting game manifest")
            self.logger.debug(response.content)
            return

        response_json = response.json()

        return response_json

    def get_patches(self, id, version, file_list):
        token = self.config.get("user", "tokens//bearer//access_token")

        request_data = {
            "Operation": "GetPatches",
            "versionId": version,
            "fileHashes": file_list,
            "deltaEncodings": ["FUEL_PATCH", "NONE"],
            "adgGoodId": id,
        }

        response = self.request_sds(
            "com.amazonaws.gearbox.softwaredistribution.service.model.SoftwareDistributionService.GetPatches",
            token,
            request_data,
        )

        if not response.ok:
            self.logger.error("There was an error getting patches")
            self.logger.debug(response.content)
            return

        response_json = response.json()

        return response_json["patches"]

    def get_versions(self, game_ids):
        token = self.config.get("user", "tokens//bearer//access_token")

        request_data = {"adgProductIds": game_ids, "Operation": "GetVersions"}

        response = self.request_sds(
            "com.amazonaws.gearbox.softwaredistribution.service.model.SoftwareDistributionService.GetVersions",
            token,
            request_data,
        )

        if not response.ok:
            self.logger.error("There was an error getting versions")
            self.logger.debug(response.content)
            return

        response_json = response.json()

        return response_json["versions"]

    def get_installed_game_info(self, id):
        installed_array = self.config.get("installed")
        if not installed_array:
            return dict()
        for game in installed_array:
            if game["id"] == id:
                return game

        return dict()
