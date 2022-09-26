#!/usr/bin/env python
import subprocess
import pytest
import os

DB_FILE = "test.db"

class TestDB:

    def setup(self):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)

    def run_script(self, commands):
        pipe = subprocess.Popen(["./db", DB_FILE], stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, universal_newlines=True)
        if isinstance(commands, list):
            commands = "\n".join(commands) + "\n"
        raw_output = pipe.communicate(commands)
        return raw_output[0].split('\n')


    def test_insert_retrieve_one_row(self):
        results = self.run_script([
            "insert 1 user1 person1@example.com",
            "select",
            ".exit",
        ])
        expected = [
            "db > Executed.",
            "db > (1, user1, person1@example.com)",
            "Executed.",
            "db > ",
        ]
        assert results == expected

    def test_table_full(self):
        script = []
        for i in range(1401):
            script.append("insert {} user{} person{}@example.com".format(i, i, i))
        script.append(".exit")
        results = self.run_script(script)  
        assert results[-3:] == [
            "db > Executed.",
            "db > Need to implement splitting internal node",
            ""
        ]

    def test_insert_strings_with_max_length(self):
        long_username = 'a' * 32
        long_email = 'a' * 255
        script = [
            "insert 1 {} {}".format(long_username, long_email),
            "select",
            ".exit"
        ]
        results = self.run_script(script)
        expected = [
            "db > Executed.",
            "db > (1, {}, {})".format(long_username, long_email),
            "Executed.",
            "db > ",
        ]
        assert results == expected

    def test_insert_strings_too_long(self):
        long_username = 'a' * 33
        long_email = 'a' * 256
        script = [
            "insert 1 {} {}".format(long_username, long_email),
            "select",
            ".exit"
        ]
        results = self.run_script(script)
        expected = [
            "db > String is too long.",
            "db > Executed.",
            "db > ",
        ]
        assert results == expected

    def test_insert_id_is_negative(self):
        script = [
            "insert -1 wyk qqq@aaa.com",
            "select",
            ".exit"
        ]
        results = self.run_script(script)
        expected = [
            "db > ID must be positive.",
            "db > Executed.",
            "db > ",
        ]
        assert results == expected

    def test_keep_data_after_close_connection(self):
        results1 = self.run_script([
            "insert 1 user1 person1@example.com",
            ".exit"
        ])
        assert results1 == [
            "db > Executed.",
            "db > "
        ]
        results2 = self.run_script([
            "select",
            ".exit"
        ])
        assert results2 == [
            "db > (1, user1, person1@example.com)",
            "Executed.",
            "db > "
        ]

    def test_print_constants(self):
        script = [
            '.constants',
            '.exit'
        ]
        results = self.run_script(script)

        assert results == [
            "db > Constants:",
            "ROW_SIZE: 293",
            "COMMON_NODE_HEADER_SIZE: 6",
            "LEAF_NODE_HEADER_SIZE: 14",
            "LEAF_NODE_CELL_SIZE: 297",
            "LEAF_NODE_SPACE_FOR_CELLS: 4082",
            "LEAF_NODE_MAX_CELLS: 13",
            "db > ",
        ]

    def test_print_one_node_bt_structure(self):
        script = []
        arr = [3, 1, 2]
        for i in arr:
            script.append("insert {} user{} person{}@example.com".format(i, i, i))
        script.append(".btree")
        script.append(".exit")
        results = self.run_script(script)

        assert results == [
            "db > Executed.",
            "db > Executed.",
            "db > Executed.",
            "db > Tree:",
            "- leaf (size 3)",
            "  - 1",
            "  - 2",
            "  - 3",
            "db > "
        ]

    def test_key_duplicate(self):
        script = [
            "insert 1 user1 person1@example.com",
            "insert 1 user1 person1@example.com",
            "select",
            ".exit"
        ]
        results = self.run_script(script)
        assert results == [
            "db > Executed.",
            "db > Error: Duplicate key.",
            "db > (1, user1, person1@example.com)",
            "Executed.",
            "db > ",
        ]

    def test_print_structure_of_three_leaf_node(self):
        script = []
        for i in range(1, 15):
            script.append("insert {} user{} person{}@example.com".format(i, i, i))
        script.append(".btree")
        script.append("insert 15 user15 person15@example.com")
        script.append(".exit")
        results = self.run_script(script)

        assert results[14:] == [
            "db > Tree:",
            "- internal (size 1)",
            "  - leaf (size 7)",
            "    - 1",
            "    - 2",
            "    - 3",
            "    - 4",
            "    - 5",
            "    - 6",      
            "    - 7",
            "  - key 7",
            "  - leaf (size 7)",
            "    - 8",
            "    - 9",
            "    - 10",
            "    - 11",
            "    - 12",
            "    - 13",
            "    - 14",
            "db > Executed.",
            "db > "
        ]

    def test_print_all_rows_in_multi_level_tree(self):
        script = []
        for i in range(1, 16):
            script.append("insert {} user{} person{}@example.com".format(i, i, i))
        script.append("select")
        script.append(".exit")
        results = self.run_script(script)

        assert results[15:] ==  [
            "db > (1, user1, person1@example.com)",
            "(2, user2, person2@example.com)",
            "(3, user3, person3@example.com)",
            "(4, user4, person4@example.com)",
            "(5, user5, person5@example.com)",
            "(6, user6, person6@example.com)",
            "(7, user7, person7@example.com)",
            "(8, user8, person8@example.com)",
            "(9, user9, person9@example.com)",
            "(10, user10, person10@example.com)",
            "(11, user11, person11@example.com)",
            "(12, user12, person12@example.com)",
            "(13, user13, person13@example.com)",
            "(14, user14, person14@example.com)",
            "(15, user15, person15@example.com)",
            "Executed.", 
            "db > "
        ]
    
    def print_structure_of_four_leaf_node_btree(self):
        script = [
            "insert 18 user18 person18@example.com",
            "insert 7 user7 person7@example.com",
            "insert 10 user10 person10@example.com",
            "insert 29 user29 person29@example.com",
            "insert 23 user23 person23@example.com",
            "insert 4 user4 person4@example.com",
            "insert 14 user14 person14@example.com",
            "insert 30 user30 person30@example.com",
            "insert 15 user15 person15@example.com",
            "insert 26 user26 person26@example.com",
            "insert 22 user22 person22@example.com",
            "insert 19 user19 person19@example.com",
            "insert 2 user2 person2@example.com",
            "insert 1 user1 person1@example.com",
            "insert 21 user21 person21@example.com",
            "insert 11 user11 person11@example.com",
            "insert 6 user6 person6@example.com",
            "insert 20 user20 person20@example.com",
            "insert 5 user5 person5@example.com",
            "insert 8 user8 person8@example.com",
            "insert 9 user9 person9@example.com",
            "insert 3 user3 person3@example.com",
            "insert 12 user12 person12@example.com",
            "insert 27 user27 person27@example.com",
            "insert 17 user17 person17@example.com",
            "insert 16 user16 person16@example.com",
            "insert 13 user13 person13@example.com",
            "insert 24 user24 person24@example.com",
            "insert 25 user25 person25@example.com",
            "insert 28 user28 person28@example.com",
            ".btree",
            ".exit"
        ]

        results = self.run_script(script)

        assert results[30:] == [
            "db > Tree:",
            "- internal (size 3)",
            "  - leaf (size 7)",
            "    - 1",
            "    - 2",
            "    - 3",
            "    - 4",
            "    - 5",
            "    - 6",
            "    - 7",
            "  - key 7",
            "  - leaf (size 8)",
            "    - 8",
            "    - 9",
            "    - 10",
            "    - 11",
            "    - 12",
            "    - 13",
            "    - 14",
            "    - 15",
            "  - key 15",
            "  - leaf (size 7)",
            "    - 16",
            "    - 17",
            "    - 18",
            "    - 19",
            "    - 20",
            "    - 21",
            "    - 22",
            "  - key 22",
            "  - leaf (size 8)",
            "    - 23",
            "    - 24",
            "    - 25",
            "    - 26",
            "    - 27",
            "    - 28",
            "    - 29",
            "    - 30",
            "db > "
        ]

if __name__ == '__main__':
    pytest.main(["-vv", "-s"])
