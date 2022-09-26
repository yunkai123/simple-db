# 第3部分-一个内存中技能添加的单表数据库

我们将从一个施加了诸多限制的小数据库开始。它：

- 支持两种操作：插入一行和打印所有行
- 仅保存在内存中（无法持久性到磁盘中）
- 支持硬编码的单表

我们的硬编码表将存储用户信息，如下所示：

|列|类型|
|-|-|
|id|integer|
|username|varchar(32)|
|email|varchar(255)|


这个模式很简单，但它使我们能够支持多种数据类型和多种大小的文本数据。

insert 语句现在将如下所示：

```
insert 1 cstack foo@bar.com
```

这意味着我们需要升级 `prepare_statement` 函数来解析参数

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

我们将这些解析后的参数存储到语句对象内的新 `Row` 数据结构中：

```c
#define COLUMN_USERNAME_SIZE 32
#define COLUMN_EMAIL_SIZE 255
typedef struct {
    uint32_t id;
    char username[COLUMN_USERNAME_SIZE];
    char email[COLUMN_EMAIL_SIZE];
} Row;

typedef struct {
    StatementType type;
    Row row_to_insert; // only used by isnert statement
} Statement;
```


现在我们需要将这些数据复制到表示数据表的数据结构中。SQLite使用B树进行快速查找、插入和删除。我们将从更简单的内容开始。B树可以将行分组到页面中，但我们这里使用数组而不是树来排列这些页面。

这是我的计划：

- 将行存储在称为页的内存块中
- 每个页面存储尽可能多的行
- 行被序列化为每个页面中的精简表示形式
- 页面仅在需要时分配
- 保留指向页面的指针的固定大小数组

首先，我们将定义行的精简表示：

```c
#define size_of_attribute(Struct, Attribute) sizeof(((Struct*)0)->Attribute)

const uint32_t ID_SIZE = size_of_attribute(Row, id);
const uint32_t USERNAME_SIZE = size_of_attribute(Row, username);
const uint32_t EMAIL_SIZE = size_of_attribute(Row, email);
const uint32_t ID_OFFSET = 0;
const uint32_t USERNAME_OFFSET = ID_OFFSET + ID_SIZE;
const uint32_t EMAIL_OFFSET = USERNAME_OFFSET + USERNAME_SIZE;
const uint32_t ROW_SIZE = ID_SIZE + USERNAME_SIZE + EMAIL_SIZE;
```

|列|大小（字节）|偏移|
|-|-|-|
|id|4|0|
|username|32|4|
|email|255|36|
|总计|291|


我们还需要代码来处理和精简表示之间的转换。

```c
void serialize_row(Row *source, void* destination) {
    memcpy(destination + ID_OFFSET, &(source->id), ID_SIZE);
    memcpy(destination + USERNAME_OFFSET, &(source->username), USERNAME_SIZE);
    memcpy(destination + EMAIL_OFFSET, &(source->email), EMAIL_SIZE);
}

void deserialize_row(void* source, Row* destination) {
    memcpy(&(destination->id), source + ID_OFFSET, ID_SIZE);
    memcpy(&(destination->username), source + USERNAME_OFFSET, USERNAME_SIZE);
    memcpy(&(destination->email), source + EMAIL_OFFSET, EMAIL_SIZE);
}
```

接下来是一个 `Table` 结构，它指向行的页面并跟踪有多少行：

```c
const uint32_t PAGE_SIZE = 4096;
#define TABLE_MAX_PAGES 100
const uint32_t ROWS_PER_PAGE = PAGE_SIZE / ROW_SIZE;
const uint32_t TABLE_MAX_ROWS = ROWS_PER_PAGE * TABLE_MAX_PAGES;

typedef struct {
    uint32_t num_rows;
    void* pages[TABLE_MAX_PAGES];
} Table;
```

我将页面大小设为4KB，因为它与大多数计算机架构的虚拟内存系统中使用的页面大小相同。这意味着数据库中的一个页面对应于操作系统使用的一个页面。操作系统将页面作为一个整体移入和移出内存，而不必将其分解。

我随意设定了一个100页限制。当我们切换到树状结构时，数据库的最大大小将仅受到文件最大大小的限制。（尽管我们仍然会限制一次在内存中保留多少页）

行不应跨越页面边界。由于页面在内存中彼此可能不会相邻，因此这种假设使读/写行变得更容易。

说到这里，我们就知道如何在内存中读取/写入特定行：

```c
void* row_slot(Table* table, uint32_t row_num) {
    uint32_t page_num = row_num / ROWS_PER_PAGE;
    void *page = table->pages[page_num];
    if(page == NULL) {
        // Allocate memory only when we try to access page
        page = table->pages[page_num] = malloc(PAGE_SIZE);
    }
    uint32_t row_offset = row_num % ROWS_PER_PAGE;
    uint32_t byte_offset = row_offset * ROW_SIZE;
    return page + byte_offset;
}
```

现在，我们可以从表结构中使用 `execute_statement` 进行读取/写入：

```c
ExecuteResult execute_insert(Statement* statement, Table* table) {
    if(table->num_rows >= TABLE_MAX_ROWS) {
        return EXECUTE_TABLE_FULL;
    }

    Row* row_to_insert = &(statement->row_to_insert);

    serialize_row(row_to_insert, row_slot(table, table->num_rows));
    table->num_rows += 1;

    return EXECUTE_SUCCESS;
}

ExecuteResult execute_select(Statement *statement, Table* table) {
    Row row;
    for(uint32_t i = 0; i < table->num_rows; i++) {
        deserialize_row(row_slot(table, i), &row);
        print_row(&row);
    }
    return EXECUTE_SUCCESS;
}

ExecuteResult execute_statement(Statement* statement, Table* table) {
    switch(statement->type) {
        case(STATEMENT_INSERT):
            return execute_insert(statement, table);
        case(STATEMENT_SELECT):
            return execute_select(statement, table);
    }
}
```

最后，我们需要初始化表，创建相应的内存释放函数，并处理更多的错误情况：

```c
Table* new_table() {
    Table* table = (Table*)malloc(sizeof(Table));
    table->num_rows = 0;
    for(uint32_t i = 0; i < TABLE_MAX_PAGES; i++) {
        table->pages[i] = NULL;
    }
    return table;
}

void free_table(Table* table) {
    for(int i = 0; table->pages[i]; i++) {
        free(table->pages[i]);
    }
    free(table);
}

MetaCommandResult do_mata_command(InputBuffer* input_buffer, Table *table) {
    if(strcmp(input_buffer->buffer, ".exit") == 0) {
        close_input_buffer(input_buffer);
        free_table(table);
        exit(EXIT_SUCCESS);
    } else {
        return META_COMMAND_UNRECOGNIZED_COMMAND;
    }
}

int main(int argc, char* argv[]) {
    Table* table = new_table();
    InputBuffer* input_buffer = new_input_buffer();
    while(true) {
        print_prompt();
        read_input(input_buffer);

        if(input_buffer->buffer[0] == '.') {
            switch(do_mata_command(input_buffer, table)) {
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
            case (PREPARE_SYNTAX_ERROR):
                printf("Syntax error. Could not parse statement.\n");
                continue;
            case (PREPARE_UNRECOGNIZED_STATEMENT):
                printf("Unrecognized keyword at start of '%s'\n",
                    input_buffer->buffer);
                continue;
        }

        switch(execute_statement(&statement, table)) {
            case (EXECUTE_SUCCESS):
                printf("Executed.\n");
                break;
            case (EXECUTE_TABLE_FULL):
                printf("Error: Table full.\n");
                break;
        }
    }
}
```

通过这些更改，我们将数据保存在数据库中！

```
~ ./db
db > insert 1 cstack foo@bar.com
Executed.
db > insert 2 bob bob@example.com
Executed.
db > select
(1, cstack, foo@bar.com)
(2, bob, bob@example.com)
Executed.
db > insert foo bar 1
Syntax error. Could not parse statement.
db > .exit
```