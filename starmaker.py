#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/9/25 下午3:11
@Author  : 刘仙辉
@File    : starmaker.py
@Desc    : 缺少印度数据，会经常中断，优化导入数据逻辑。
"""
import time
import logging
from typing import Optional, Dict, Any, List
from configparser import ConfigParser
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

import requests
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

disable_warnings(InsecureRequestWarning)

from tools import create_params

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Starmaker:
    def __init__(self, config: Dict[str, str]):
        """
        Initialize Starmaker client with MongoDB connection

        Args:
            config: Configuration dictionary with mongodb_link and mongodb_database
        """
        try:
            self.client = MongoClient(config['mongodb_link'])
            self.db = self.client[config['mongodb_database']]
            self.performance = self.db['performance']
            self.comment = self.db['comment']
            self.user = self.db['user']
            self.followers_wees = self.db['followers_wees']

            # Create indexes for better performance
            self._create_indexes()

            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _create_indexes(self):
        """Create necessary indexes for better query performance"""
        try:
            self.user.create_index([("id", 1)], unique=True)
            self.performance.create_index([("sm_id", 1)], unique=True)
            self.performance.create_index([("is_use", 1)])
            self.comment.create_index([("comment_id", 1)], unique=True)
            self.followers_wees.create_index([("f_user_id", 1), ("type", 1)])
            logger.info("Database indexes created successfully")
        except PyMongoError as e:
            logger.warning(f"Failed to create indexes: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic

        Args:
            url: Request URL
            params: Request parameters

        Returns:
            Response object or None if failed
        """
        headers = create_params(url=url, params=params)
        response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
        response.raise_for_status()
        return response

    def user_info(self, user_id: int) -> bool:
        """
        Fetch and store user information

        Args:
            user_id: User ID to fetch

        Returns:
            bool: Success status
        """
        if not user_id:
            return False

        url = f"https://api.starmakerstudios.com/api/v17/android/sm/us/phone/xhdpi/users/profile/{user_id}"
        params = {
            "phone_brand": "samsung",
            "phone_model": "SM-G9810",
            "phone_manufacturer": "samsung",
            "performance_level": "2"
        }

        try:
            response = self._make_request(url, params)
            if response and response.status_code == 200:
                user_data = response.json().get("user")
                if user_data:
                    user_data['is_use'] = 0
                    self.user.update_one(
                        {"id": str(user_id)},
                        {"$set": user_data},
                        upsert=True
                    )
                    logger.info(f"Successfully inserted/updated user {user_id}")
                    time.sleep(0.5)  # Reduced sleep time
                    return True
        except Exception as e:
            logger.error(f"Failed to fetch user {user_id}: {e}")

        return False

    def per_list(self, user_id: Optional[int] = None) -> None:
        """
        Fetch user's performance list

        Args:
            user_id: Specific user ID to fetch, if None fetches from database
        """
        if user_id:
            users_to_process = [{"id": user_id}]
        else:
            users_to_process = self.user.find(
                {"is_use": 0},
                {"id": 1, "_id": 0}
            ).limit(100)  # Limit batch size

        for user_doc in users_to_process:
            user_id = user_doc.get('id')
            if not user_id:
                continue

            next_cursor = 0
            max_retries = 3
            retry_count = 0

            while True:
                url = f"https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/users/{user_id}/recordings"
                params = {
                    "next_cursor": next_cursor,
                    "skip_id": 0
                }

                try:
                    response = self._make_request(url, params)
                    if not response or response.status_code != 200:
                        retry_count += 1
                        if retry_count >= max_retries:
                            break
                        time.sleep(2)
                        continue

                    json_res = response.json()
                    total = json_res.get("total", 0)

                    if total == 0:
                        break

                    recording_list = json_res.get("recording_list", [])
                    if not recording_list:
                        break

                    # Prepare records for insertion
                    records_to_insert = []
                    for record in recording_list:
                        if 'recording' in record:
                            record['user_id'] = user_id
                            record['sm_id'] = record['recording']['sm_id']
                            record['is_use'] = 0
                            records_to_insert.append(record)

                    if records_to_insert:
                        try:
                            self.performance.insert_many(records_to_insert, ordered=False)
                            logger.info(f"Inserted {len(records_to_insert)} performances for user {user_id}")
                        except PyMongoError as e:
                            logger.error(f"Failed to insert performances for user {user_id}: {e}")

                    next_cursor += 15
                    retry_count = 0  # Reset retry count on success
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error fetching performances for user {user_id}: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        break
                    time.sleep(2)

            # Mark user as processed
            self.user.update_one({"id": str(user_id)}, {"$set": {"is_use": 1}})
            logger.info(f"Completed fetching performances for user {user_id}")

    def comment(self, batch_size: int = 50) -> None:
        """
        Fetch comments for performances

        Args:
            batch_size: Number of records to process in one batch
        """
        query = {
            "is_use": 0,
            "recording.num_comments": {"$gt": 0}
        }

        performances = self.performance.find(query, {"sm_id": 1, "_id": 0, "recording.num_comments": 1}).limit(
            batch_size)

        for performance_doc in performances:
            sm_id = performance_doc.get('sm_id')
            recording = performance_doc.get('recording', {})

            if not sm_id or not recording:
                continue

            num_comments = recording.get("num_comments", 0)
            if num_comments == 0:
                continue

            url = "https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/comment/level-comments"
            params = {
                "sm_id": sm_id,
                "limit": min(num_comments, 100),  # Limit to 100 comments per request
                "except_ids": "",
                "created_on": "0"
            }

            try:
                response = self._make_request(url, params)
                if response and response.status_code == 200:
                    res = response.json()
                    items = res.get("items", [])

                    if items:
                        try:
                            self.comment.insert_many(items, ordered=False)
                            logger.info(f"Inserted {len(items)} comments for performance {sm_id}")

                            # Fetch user info for commenters
                            for item in items[:10]:  # Limit to first 10 to avoid too many requests
                                user_id = item.get("user_id")
                                if user_id:
                                    self.user_info(user_id)

                        except PyMongoError as e:
                            logger.error(f"Failed to insert comments for {sm_id}: {e}")

                    # Mark performance as processed
                    self.performance.update_one({"sm_id": sm_id}, {"$set": {"is_use": 1}})

            except Exception as e:
                logger.error(f"Failed to fetch comments for {sm_id}: {e}")

            time.sleep(0.5)

    def discover(self, max_pages: int = 10) -> None:
        """
        Discover and fetch users from home feed

        Args:
            max_pages: Maximum number of pages to fetch
        """
        for page in range(1, max_pages + 1):
            url = "https://api.starmakerstudios.com/api/v17/android/sm/en/phone/xhdpi/moment/square/recommend"
            params = {
                "label_id": "0",
                "label_type": "hot",
                "page": str(page),
                "is_first": 'false' if page > 1 else 'true',
                "is_feed_mine_top": "1"
            }

            try:
                response = self._make_request(url, params)
                if response and response.status_code == 200:
                    data = response.json()
                    items_list = data.get("items", [])

                    if not items_list:
                        break

                    for item in items_list:
                        sm = item.get("sm", {})
                        user_id = sm.get("user_id")
                        if user_id:
                            self.user_info(user_id)

                    logger.info(f"Processed page {page} of discover feed")

            except Exception as e:
                logger.error(f"Failed to fetch discover page {page}: {e}")

            time.sleep(0.5)

    def followers_wees(self, batch_size: int = 50) -> None:
        """
        Fetch followers and followees for users

        Args:
            batch_size: Number of users to process in one batch
        """
        users = self.user.find({"fis_use": 0}, {"id": 1, "_id": 0}).limit(batch_size)

        for user_doc in users:
            user_id = user_doc.get("id")
            if not user_id:
                continue

            url_types = {
                "followers": f"https://api.starmakerstudios.com/api/v17/android/sm/zh-CN/phone/xhdpi/users/{user_id}/followers",
                "followees": f"https://api.starmakerstudios.com/api/v17/android/sm/zh-CN/phone/xhdpi/users/{user_id}/followees"
            }

            for relation_type, url in url_types.items():
                page = 0
                max_pages = 10  # Limit pages to avoid infinite loops

                for page in range(max_pages):
                    params = {"page": page}

                    try:
                        response = self._make_request(url, params)
                        if not response or response.status_code != 200:
                            break

                        res = response.json()
                        callback = res.get("callback")

                        if not callback:
                            break

                        user_list = res.get("user_list", [])
                        if not user_list:
                            break

                        # Prepare records for insertion
                        records_to_insert = []
                        for user in user_list:
                            user['f_user_id'] = user_id
                            user['type'] = relation_type
                            records_to_insert.append(user)

                        if records_to_insert:
                            try:
                                self.followers_wees.insert_many(records_to_insert, ordered=False)
                                logger.info(f"Inserted {len(records_to_insert)} {relation_type} for user {user_id}")
                            except PyMongoError as e:
                                logger.error(f"Failed to insert {relation_type} for user {user_id}: {e}")

                        time.sleep(0.5)

                    except Exception as e:
                        logger.error(f"Failed to fetch {relation_type} for user {user_id} (page {page}): {e}")
                        break

            # Mark user as processed
            self.user.update_one({"id": user_id}, {"$set": {"fis_use": 1}})
            logger.info(f"Completed fetching followers/followees for user {user_id}")

    def process_users_from_file(self, file_path: str = 'unique_real_action_users.txt') -> None:
        """
        Process users from a text file

        Args:
            file_path: Path to the user IDs file
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                user_ids = [line.strip() for line in file if line.strip()]

            logger.info(f"Processing {len(user_ids)} users from file")

            for user_id in user_ids:
                try:
                    self.user_info(int(user_id))
                except ValueError:
                    logger.warning(f"Invalid user ID: {user_id}")
                except Exception as e:
                    logger.error(f"Failed to process user {user_id}: {e}")

                time.sleep(0.5)

        except FileNotFoundError:
            logger.warning(f"File {file_path} not found")
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")

    def run(self, max_iterations: int = 2) -> None:
        """
        Main execution loop

        Args:
            max_iterations: Maximum number of iterations to run
        """
        for iteration in range(max_iterations):
            logger.info(f"Starting iteration {iteration + 1}/{max_iterations}")

            try:
                # Step 1: Discover new users
                self.discover(max_pages=5)

                # Step 2: Fetch followers/followees
                # self.followers_wees()

                # Step 3: Fetch performances
                self.per_list()

                # Step 4: Fetch comments
                self.comment()

                logger.info(f"Completed iteration {iteration + 1}")

            except Exception as e:
                logger.error(f"Error in iteration {iteration + 1}: {e}")
                continue

        # Final processing from file
        self.process_users_from_file()

        # Close MongoDB connection
        self.client.close()
        logger.info("Completed all operations")


if __name__ == '__main__':
    from db_config import MONGO_DB, MONGO_URI
    config = {
        "mongodb_link": MONGO_URI,
        "mongodb_database": MONGO_DB,
    }

    sm = Starmaker(config)
    # You can run specific methods or the full pipeline
    # sm.discover(max_pages=5)
    # sm.per_list()  # This will process users from database with is_use=0
    sm.run(max_iterations=2)