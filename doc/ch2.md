# 第2部分-世界上最简单的SQL编译器和虚拟机

我们正在复制 sqlite。sqlite的“前台”是一个SQL编译器，它解析字符串并输出称为字节码的内部表示。

该字节码被传递给虚拟机，由虚拟机执行。

![](/img/sqlite-architecture2.gif)

将事情分成两个步骤有两个优点：

- 降低每个部分的复杂性（例如，虚拟机不担心语法错误）。
- 允许只编译一次常见查询，并缓存字节码以提高性能。

考虑到这一点，让我们重构我们的主函数，并在此过程中支持两个新的关键字：

```c
int main(int argc, char* argv[]) {
    InputBuffer* input_buffer = new_input_buffer();
    while(true) {
        print_prompt();
        read_input(input_buffer);

        if(input_buffer->buffer[0] == '.') {
            switch(do_mata_command(input_buffer)) {
                case (META_COMMAND_SUCCESS):
                    continue;
                case (META_COMMAND_UNRECOGNIZED_COMMAND):
                    printf("Unrecognized command '%s'\n", input_buffer->buffer);
                    continue;
            }
        } 

        Statement statement;
        switch(prepare_statement(input_buffer, &statement)) {
            case (PREPARE_SUCCESS):
                break;
            case (PREPARE_UNRECOGNIZED_STATEMENT):
                printf("Unrecognized keyword at start of '%s'\n",
                    input_buffer->buffer);
                continue;
        }

        execute_statement(&statement);
        printf("Executed.\n");
    }
}
```


非SQL语句，如 `.exit`，称为“元命令”。它们都以一个点开始，所以我们检查它们并在一个单独的函数中处理它们。

接下来，我们添加一个步骤，将输入行转换为内部的语句。

最后，我们将准备好的语句传递给 `execute_statement`。这个函数最终将成为我们的虚拟机。

请注意，我们的两个新函数返回表示成功或失败的枚举：

```c
typedef enum {
    META_COMMAND_SUCCESS,
    META_COMMAND_UNRECOGNIZED_COMMAND
} MetaCommandResult;

typedef enum {
    PREPARE_SUCCESS,
    PREPARE_UNRECOGNIZED_STATEMENT
} PrepareResult;
```


“无法识别的语句”？这似乎有点像一个异常。我不喜欢使用异常（C甚至不支持它们），所以我尽可能对结果代码使用枚举。如果我的 `switch` 语句没有处理枚举的一个成员，C编译器会进行提示，因此我们可以对处理函数的每个结果更有信心。预计将来会添加更多结果代码。

`do_meta_command` 命令只是现有功能的包装，为更多命令留出了空间：

```c
MetaCommandResult do_mata_command(InputBuffer* input_buffer) {
    if(strcmp(input_buffer->buffer, ".exit") == 0) {
        exit(EXIT_SUCCESS);
    } else {
        return META_COMMAND_UNRECOGNIZED_COMMAND;
    }
}
```

我们现在的“prepared statement”只包含一个具有两个可能值的枚举。它将包含更多数据，因为我们允许语句中包含参数：

```c
typedef enum {
    STATEMENT_INSERT,
    STATEMENT_SELECT
} StatementType;

typedef struct {
    StatementType type;
} Statement;
```


`prepare_statement`（我们的“SQL编译器”）目前还无法解析 SQL。事实上，它只理解两个词：

```c
PrepareResult prepare_statement(InputBuffer* input_buffer,
                                Statement* statement) {
    if(strncmp(input_buffer->buffer, "insert", 6) == 0) {
        statement->type = STATEMENT_INSERT;
        return PREPARE_SUCCESS;
    }
    if(strcmp(input_buffer->buffer, "select") == 0) {
        statement->type = STATEMENT_SELECT;
        return PREPARE_SUCCESS;
    }

    return PREPARE_UNRECOGNIZED_STATEMENT;
}
```

注意，我们使用 `strncmp` 识别 “insert”，因为“insert”关键字后面跟着数据。

最后，`execute_statement` 包含以下部分：

```c
void execute_statement(Statement* statement) {
    switch(statement->type) {
        case(STATEMENT_INSERT):
            printf("This is where we would do an insert.\n");
            break;
        case(STATEMENT_SELECT):
            printf("This is where we would do an select.\n");
            break;
    }
}
```

注意，它不会返回任何错误代码，因为还没有任何可能出错的地方。

通过这些重构，我们现在可以识别两个新的关键字！


我们数据库的骨架正在成形...如果它可以存储数据不是更好吗？在下一部分中，我们将实现 insert 和 select，创建世界上最差的数据存储。同时，这是这一部分的全部代码：

```c
'''

} InputBuffer;

typedef enum {
    META_COMMAND_SUCCESS,
    META_COMMAND_UNRECOGNIZED_COMMAND
} MetaCommandResult;

typedef enum {
    PREPARE_SUCCESS,
    PREPARE_UNRECOGNIZED_STATEMENT
} PrepareResult;

typedef enum {
    STATEMENT_INSERT,
    STATEMENT_SELECT
} StatementType;

typedef struct {
    StatementType type;
} Statement;

InputBuffer* new_input_buffer() {
    InputBuffer* input_buffer = malloc(sizeof(InputBuffer));
    input_buffer->buffer = NULL;
    input_buffer->buffer_length = 0;
    input_buffer->input_length = 0;

    return input_buffer;
}

MetaCommandResult do_mata_command(InputBuffer* input_buffer) {
    if(strcmp(input_buffer->buffer, ".exit") == 0) {
        exit(EXIT_SUCCESS);
    } else {
        return META_COMMAND_UNRECOGNIZED_COMMAND;
    }
}

PrepareResult prepare_statement(InputBuffer* input_buffer,
                                Statement* statement) {
    if(strncmp(input_buffer->buffer, "insert", 6) == 0) {
        statement->type = STATEMENT_INSERT;
        return PREPARE_SUCCESS;
    }
    if(strcmp(input_buffer->buffer, "select") == 0) {
        statement->type = STATEMENT_SELECT;
        return PREPARE_SUCCESS;
    }

    return PREPARE_UNRECOGNIZED_STATEMENT;
}

void execute_statement(Statement* statement) {
    switch(statement->type) {
        case(STATEMENT_INSERT):
            printf("This is where we would do an insert.\n");
            break;
        case(STATEMENT_SELECT):
            printf("This is where we would do an select.\n");
            break;
    }
}

void print_prompt() {
    printf("db > ");
}

void read_input(InputBuffer* input_buffer) {
    ssize_t bytes_read = getline(&(input_buffer->buffer), &(input_buffer->buffer_length), stdin);

    if(bytes_read <= 0) {
        printf("Error reading input\n");
        exit(EXIT_FAILURE);
    }

    input_buffer->input_length = bytes_read - 1;
    input_buffer->buffer[bytes_read - 1] = 0;
}

void close_input_buffer(InputBuffer* input_buffer) {
    free(input_buffer->buffer);
    free(input_buffer);
}

int main(int argc, char* argv[]) {
    InputBuffer* input_buffer = new_input_buffer();
    while(true) {
        print_prompt();
        read_input(input_buffer);

        if(input_buffer->buffer[0] == '.') {
            switch(do_mata_command(input_buffer)) {
                case (META_COMMAND_SUCCESS):
                    continue;
                case (META_COMMAND_UNRECOGNIZED_COMMAND):
                    printf("Unrecognized command '%s'\n", input_buffer->buffer);
                    continue;
            }
        } 

        Statement statement;
        switch(prepare_statement(input_buffer, &statement)) {
            case (PREPARE_SUCCESS):
                break;
            case (PREPARE_UNRECOGNIZED_STATEMENT):
                printf("Unrecognized keyword at start of '%s'\n",
                    input_buffer->buffer);
                continue;
        }

        execute_statement(&statement);
        printf("Executed.\n");
    }
}
```