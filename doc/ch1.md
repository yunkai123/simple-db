# 第1部分-介绍和设置REPL

作为一名 Web 开发人员，我在工作中每天都在使用关系数据库，但我对它们的原理一无所知。我有一些问题：

- 数据（在内存和磁盘中）保存的格式是什么？
- 它什么时候从内存移动到磁盘？
- 为什么每个表只能有一个主键？
- 回滚事务是如何工作的？
- 索引是如何格式化的？
- 何时以及如何进行全表扫描？
- 准备好的语句以什么格式保存？

换句话说，数据库是如何**工作**的？

为了找到答案，我正在从头开始编写一个数据库。它以 sqlite 为模型，因为 sqlite 相比 MySQL 或 PostgreSQL 更小，功能更少，所以理解它更容易。另外，它的整个数据库存储在一个文件中！

## Sqlite

他们的网站上有很多关于sqlite内部的[文档](https://www.sqlite.org/arch.html)，另外我还有一份SQLite Database System: Design and Implementation。

![](/img/sqlite-architecture.gif)

查询（query）通过一系列组件来检索或修改数据。**前台**包括：

- 标记器（tokenizer）
- 解析器（parser）
- 代码生成器（code generator）

前台的输入是一个 SQL 查询。输出是 sqlite 虚拟机字节码（本质上是可以在数据库上操作的编译程序）。

后台包括：

- 虚拟机
- B树
- 分页器（pager）
- 操作系统接口

**虚拟机**将前台生成的字节码作为指令。然后，它可以对一个或多个表或索引执行操作，每个表或索引都存储在称为B树的数据结构中。虚拟机本质上是字节码指令类型上的一个大的 switch 语句。

每个**B树**由许多节点组成。每个节点的长度为一页。B树可以从磁盘检索页面，或通过向pager发出命令将其保存回磁盘。

**分页器**接收读取或写入数据页的命令。它负责以适当的偏移量读取/写入数据库文件。它还将最近访问的页面缓存在内存中，并确定何时需要将这些页面写回磁盘。

**操作系统接口**取决于编译sqlite的操作系统。本教程中不会支持多个平台。

千里之行始于足下，所以让我们从最简单的事情开始：REPL。

## 制作简单的REPL

当您从命令行启动 sqlite 时，它会启动一个读-执行-打印循环：

```
~ sqlite3
SQLite version 3.16.0 2016-11-04 19:09:39
Enter ".help" for usage hints.
Connected to a transient in-memory database.
Use ".open FILENAME" to reopen on a persistent database.
sqlite> create table users (id int, username varchar(255), email varchar(255));
sqlite> .tables
users
sqlite> .exit
~
```

为实现此效果，我们的主函数将有一个无限循环，该循环打印提示，获取一行输入，然后处理该行输入：

```c
int main(int argc, char* argv[]) {
    InputBuffer* input_buffer = new_input_buffer();
    while(true) {
        print_prompt();
        read_input(input_buffer);

        if(strcmp(input_buffer->buffer, ".exit") == 0) {
            close_input_buffer(input_buffer);
            exit(EXIT_SUCCESS);
        } else {
            printf("Unrecognized command '%s'.\n", input_buffer->buffer);
        }
    }
}
```



我们将 `InputBuffer` 定义为与 `getline()` 交互所需存储状态的小包装器。（稍后将详细介绍）:

```c
typedef struct {
    char* buffer;
    size_t buffer_length;
    ssize_t input_length;
} InputBuffer;

InputBuffer* new_input_buffer() {
    InputBuffer* input_buffer = malloc(sizeof(InputBuffer));
    input_buffer->buffer = NULL;
    input_buffer->buffer_length = 0;
    input_buffer->input_length = 0;

    return input_buffer;
}
```


接下来，`print_prompt()` 向用户打印提示。我们在每一行输入之前都会打印。

```c
void print_prompt() {
    printf("db > ");
}
```

要读取一行输入，请使用 `getline()`：

```c
ssize_t getline(char **lineptr, size_t *n, FILE *stream);
```

lineptr：指向包含读取行的缓冲区的变量的指针。如果将其设置为 `NULL`，则 `getline` 会将其定位错误，因此即使命令失败，用户也应将其释放。

n：指向我们用来保存分配缓冲区大小的变量的指针。

stream ：要从中读取的输入流。我们将从标准输入中读取。

返回值：读取的字节数，可能小于缓冲区的大小。

我们告诉 `getline` 将读取行存储在 `input_buffer->buffer` 中，并将分配的缓冲区大小存储在`input_buffer->buffer_length` 中。我们将返回值存储在 `input_buffer->input_length` 中。

`buffer`以 null 开始，因此 `getline` 分配足够的内存来容纳输入行，并使 `buffer` 指向它。

```c
void read_input(InputBuffer* input_buffer) {
    ssize_t bytes_read = getline(&(input_buffer->buffer), &(input_buffer->buffer_length), stdin);

    if(bytes_read <= 0) {
        printf("Error reading input\n");
        exit(EXIT_FAILURE);
    }

    input_buffer->input_length = bytes_read - 1;
    input_buffer->buffer[bytes_read - 1] = 0;
}
```

现在可以定义一个函数来释放为 `InputBuffer*` 实例和相应结构的 `buffer` 元素分配的内存（getline 在 `read_input`中为 ` input_buffer->buffer` 分配内存）。

```c
void close_input_buffer(InputBuffer* input_buffer) {
    free(input_buffer->buffer);
    free(input_buffer);
}
```

最后，我们解析并执行该命令。目前只有一个可识别的命令： `.exit`，终止程序。否则，我们打印错误消息并继续循环。

让我们试试吧！

好的，我们有了一个可以运行的REPL。在下一部分中，我们将开始开发命令语言。以下是这一部分的整个程序：

```c
#include<stdbool.h>
#include<stdio.h>
#include<stdlib.h>
#include<string.h>

typedef struct {
    char* buffer;
    size_t buffer_length;
    ssize_t input_length;
} InputBuffer;

InputBuffer* new_input_buffer() {
    InputBuffer* input_buffer = malloc(sizeof(InputBuffer));
    input_buffer->buffer = NULL;
    input_buffer->buffer_length = 0;
    input_buffer->input_length = 0;

    return input_buffer;
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

        if(strcmp(input_buffer->buffer, ".exit") == 0) {
            close_input_buffer(input_buffer);
            exit(EXIT_SUCCESS);
        } else {
            printf("Unrecognized command '%s'.\n", input_buffer->buffer);
        }
    }
}
```