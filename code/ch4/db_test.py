#!/usr/bin/env python
import subprocess
import pytest

class TestDB:

    def run_script(self, commands):
        pipe = subprocess.Popen(["./db"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
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
        assert results[-2] == 'db > Error: Table full.'

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


if __name__ == '__main__':
    pytest.main(["-vv", "-s"])



