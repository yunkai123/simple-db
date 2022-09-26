# 第4部分-我们的第一个测试（和缺陷）

我们能够将行插入数据库并打印出所有行。让我们花一点时间来测试我们到目前为止的程序。

我将使用 Python 测试框架 pytest 来进行测试。原文使用[rspec](http://rspec.info/)来编写测试，它是一个 Ruby 语言的测试框架，具有很强的可读性。由于我不是很擅长 Ruby，改成了自己更熟悉的 Python。

这里将定义一个简短的辅助脚本 `db_test.py`，将命令列表发送到我们的数据库程序，然后对输出进行断言：

```py
import subprocess
import pytest

class TestDB:

    def run_script(self, commands):
        pipe = subprocess.Popen(["./db"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, universal_newlines=True)
        if isinstance(commands, list):
            commands = "\n".join(commands) + "\n"
        os.set_blocking(pipe.stdout.fileno(), False)
        raw_output = pipe.communicate(commands)
        #print(raw_output)
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
```

这个简单的测试可以确保我们得到想要的东西。它也确实通过了（注意运行之前需要先将我们的数据库程序编译成成可执行文件 `db`）：

```
$ python3 db_test.py
...                                                                                                   
db_test.py::TestDB::test_insert_retrieve_one_row PASSED

```

现在可以测试在数据库中插入大量行：

```py
    def test_table_full(self):
        script = []
        for i in range(1401):
            script.append("insert {} user{} person{}@example.com".format(i, i, i))
        script.append(".exit")
        results = self.run_script(script)  
        assert results[-2] == 'db > Error: Table full.'
```

再次运行测试...

```
$python3 db_test.py
...

db_test.py::TestDB::test_insert_retrieve_one_row PASSED
db_test.py::TestDB::test_table_full PASSED
```

好极了，运行正常！我们的数据库现在可以容纳1400行，因为我们将最大页数设置为100，一个页面可以容纳14行。

阅读到目前为止的代码，我意识到我们可能无法正确存储文本字段。如下例子可以测试：

```py
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
```

测试失败了！

```
$python3 db_test.py
...

db_test.py::TestDB::test_insert_retrieve_one_row PASSED
db_test.py::TestDB::test_table_full PASSED
db_test.py::TestDB::test_insert_strings_with_max_length FAILED
```
查看失败信息。

```
At index 1 diff: 'db > (1, aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)' != 'db > (1, aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)'

```

测试失败了！用户名的长度远超预期（这里和原文中出现乱码的表现不同）。

怎么回事？如果你看一下我们对行的定义，我们为用户名分配了32个字节，为电子邮件分配了255个字节。但是C字符串应该以 null 结尾，我们没有为其分配空间。所以用户名和电子邮箱连在了一起，导致用户名的长度达到了287（32+255）。

解决方案是再分配一个字节：

```c
#define COLUMN_USERNAME_SIZE 32
#define COLUMN_EMAIL_SIZE 255
typedef struct {
    uint32_t id;
    char username[COLUMN_USERNAME_SIZE + 1];
    char email[COLUMN_EMAIL_SIZE + 1];
} Row;
```


问题就得到了解决。


我们不应该允许插入超过列大小的用户名或电子邮件。其测试用例如下所示：


为了做到这一点，我们需要升级解析器。提醒一下，我们目前正在使用 `scanf()`：

```c
    if(strncmp(input_buffer->buffer, "insert", 6) == 0) {
        statement->type = STATEMENT_INSERT;
        int args_assigned = sscanf(
            input_buffer->buffer, "insert %d %s %s", &(statement->row_to_insert.id),
            statement->row_to_insert.username, statement->row_to_insert.email
        );
        if(args_assigned < 3) {
            return PREPARE_SYNTAX_ERROR;
        }
        return PREPARE_SUCCESS;
    }
```

但是 `scanf` 有一些缺点。如果它读取的字符串长度大于缓冲区长度，则会导致缓冲区溢出，并开始写入意外的位置。我们希望在将每个字符串复制到 `Row` 结构之前检查其长度。为此，我们需要将输入以空格分割。

我将使用 `strtok()` 来实现这一点。你看到它的实际应用会更加容易理解：

```c
PrepareResult prepare_insert(InputBuffer* input_buffer, Statement* statement) {
    statement->type = STATEMENT_INSERT;

    char* keyword = strtok(input_buffer->buffer, " ");
    char* id_string = strtok(NULL, " ");
    char* username = strtok(NULL, " ");
    char* email = strtok(NULL, " ");

    if(id_string == NULL || username == NULL || email == NULL) {
        return PREPARE_SYNTAX_ERROR;
    }

    int id = atoi(id_string);
    if(strlen(username) > COLUMN_USERNAME_SIZE) {
        return PREPARE_STRING_TOO_LONG;
    }
    if(strlen(email) > COLUMN_EMAIL_SIZE) {
        return PREPARE_STRING_TOO_LONG;
    }

    statement->row_to_insert.id = id;
    strcpy(statement->row_to_insert.username, username);
    strcpy(statement->row_to_insert.email, email);

    return PREPARE_SUCCESS;
}

PrepareResult prepare_statement(InputBuffer* input_buffer,
                                Statement* statement) {
    if(strncmp(input_buffer->buffer, "insert", 6) == 0) {
        return prepare_insert(input_buffer, statement);       
    }
    if(strcmp(input_buffer->buffer, "select") == 0) {
        statement->type = STATEMENT_SELECT;
        return PREPARE_SUCCESS;
    }

    return PREPARE_UNRECOGNIZED_STATEMENT;
}
```

在输入缓冲区上连续调用 `strtok` 会通过在到达分隔符（在本例中为空格）时插入空字符将其拆分为子字符串。它返回指向子字符串开头的指针。

我们可以对每个文本值调用 `strlen()`，看看它是否太长。

我们可以像处理任何其他错误代码一样处理错误：

```c
typedef enum {
    PREPARE_SUCCESS,
    PREPARE_STRING_TOO_LONG,
    PREPARE_SYNTAX_ERROR,
    PREPARE_UNRECOGNIZED_STATEMENT    
} PrepareResult;

...

        switch(prepare_statement(input_buffer, &statement)) {
            case (PREPARE_SUCCESS):
                break;
            case (PREPARE_STRING_TOO_LONG):
                printf("String is too long.\n");
                continue;
            case (PREPARE_SYNTAX_ERROR):
                printf("Syntax error. Could not parse statement.\n");
                continue;
            case (PREPARE_UNRECOGNIZED_STATEMENT):
                printf("Unrecognized keyword at start of '%s'\n",
                    input_buffer->buffer);
                continue;
        }
```

这让我们的测试通过了:

```
$ python3 db_test.py
...                                                                                                 
db_test.py::TestDB::test_insert_retrieve_one_row PASSED
db_test.py::TestDB::test_table_full PASSED
db_test.py::TestDB::test_insert_strings_with_max_length PASSED
db_test.py::TestDB::test_insert_strings_too_long PASSED
```

在这里，我们不妨再处理一个错误案例：

```py
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
```

```c
typedef enum {
    PREPARE_SUCCESS,
    PREPARE_NEGATIVE_ID,
    PREPARE_STRING_TOO_LONG,
    PREPARE_SYNTAX_ERROR,
    PREPARE_UNRECOGNIZED_STATEMENT    
} PrepareResult;

...

    int id = atoi(id_string);
    if(id < 0) {
        return PREPARE_NEGATIVE_ID;
    }

...

        switch(prepare_statement(input_buffer, &statement)) {
            case (PREPARE_SUCCESS):
                break;
            case (PREPARE_NEGATIVE_ID):
                printf("ID must be positive.\n");
                continue;
            case (PREPARE_STRING_TOO_LONG):
                printf("String is too long.\n");
                continue;

...
```

好了，测试案例已经够了。接下来是一个非常重要的特性：持久性！我们将把数据库保存到一个文件中，然后重新读取。

这会很棒！
