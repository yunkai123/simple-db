# 第5部分-持久化到磁盘

*“Nothing in the world can take the place of persistence.” – Calvin Coolidge*

我们的数据库允许插入记录并进行读取，但前提是你保持程序运行。如果你关闭程序并重新启动，所有的记录都会消失。以下是我们的测试案例：

```py
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
```

像sqlite一样，我们将通过将整个数据库保存到一个文件来持久化记录。

我们已经通过将行序列化为页面大小的内存块。为了增加持久性，我们可以简单地将这些内存块写入一个文件，并在下次程序启动时将其读回内存。

为了简化这个过程，我们将制作一个抽象层，称为页面处理器（pager）。我们向页面处理器请求第x页，页面处理器会返回一块内存。它首先在缓存中查找。在缓存未命中时，它将数据从磁盘复制到内存中（通过读取数据库文件）。

![](/img/arch-part5.gif)

页面处理器访问页面缓存和文件。Table 对象通过页面处理器请求页面：

```c
typedef struct {
    int file_descriptor;
    uint32_t file_length;
    void* pages[TABLE_MAX_PAGES];
} Pager;

typedef struct {
    uint32_t num_rows;
    Pager* pager;
} Table;
```

我将 `new_table()` 重命名为 `db_open()`，因为它现在可以打开与数据库的连接。通过打开连接，我们会：

- 打开数据库文件
- 初始化一个 pager 数据结构
- 初始化一个 table 数据结构

```c
Table* db_open(const char* filename) {
    Pager* pager = pager_open(filename);
    uint32_t num_rows = pager->file_length / ROW_SIZE;

    Table* table = malloc(sizeof(Table));
    table->pager = pager;
    table->num_rows = num_rows;

    return table;
}
```

`db_open()` 反过来调用 `pager_open()`，后者打开数据库文件并跟踪其大小。它还将所有页面缓存初始化为 `NULL`。

```c
Pager* pager_open(const char* filename) {
    int fd = open(filename, O_RDWR | O_CREAT, S_IWUSR | S_IRUSR);
    if(fd == -1) {
        printf("Unable to open file\n");
        exit(EXIT_FAILURE);
    } 

    off_t file_length = lseek(fd, 0, SEEK_END);

    Pager* pager = malloc(sizeof(Pager));
    pager->file_descriptor = fd;
    pager->file_length = file_length;

    for(uint32_t i = 0; i < TABLE_MAX_PAGES; i++) {
        pager->pages[i] = NULL;
    }
    return pager;
}
```

有了新的抽象层之后，我们将获取页面的逻辑转移到它自己的方法中：

```c
void* row_slot(Table* table, uint32_t row_num) {
    uint32_t page_num = row_num / ROWS_PER_PAGE;
    void *page = get_page(table->pager, page_num);
  
    uint32_t row_offset = row_num % ROWS_PER_PAGE;
    uint32_t byte_offset = row_offset * ROW_SIZE;
    return page + byte_offset;
}
```

`get_page()` 方法具有处理缓存未命中的逻辑。我们假设页面在数据库文件中一个接一个地保存：第0页的偏移量为0，第1页的偏移量为4096，第2页的偏移量为8192，以此类推。如果请求的页面位于文件的边界之外，我们知道它应该是空白的，所以我们只需分配一些内存并返回它。当我们稍后将缓存刷新到磁盘时，页面将添加到文件中。

```c
void* get_page(Pager* pager, uint32_t page_num) {
    if(page_num > TABLE_MAX_PAGES) {
        printf("Tried to fetch page number out of bounds. %d > %d\n", page_num,
            TABLE_MAX_PAGES);
        exit(EXIT_FAILURE);
    }

    if(pager->pages[page_num] == NULL) {
        // Cache miss, Allocate memory and load from file.
        void* page = malloc(PAGE_SIZE);
        uint32_t num_pages = pager->file_length / PAGE_SIZE;

        // we might save a partial page at the end of the file
        if(pager->file_length % PAGE_SIZE) {
            num_pages += 1;
        }

        if(page_num <= num_pages) {
            lseek(pager->file_descriptor, page_num * PAGE_SIZE, SEEK_SET);
            ssize_t bytes_read = read(pager->file_descriptor, page, PAGE_SIZE);
            if(bytes_read == -1) {
                printf("Error reading file: %d\n", errno);
                exit(EXIT_FAILURE);
            }
        }

        pager->pages[page_num] = page;
    }

    return pager->pages[page_num];
}
```


目前，我们将等待将缓存刷新到磁盘，直到用户关闭与数据库的连接。当用户退出时，我们将调用一个名为 `db_close()` 的新方法，该方法

- 将页面缓存刷新到磁盘
- 关闭数据库文件
- 释放 Pager 和 Table 数据结构的内存

```c
void db_close(Table* table) {
    Pager* pager = table->pager;
    uint32_t num_full_pages = table->num_rows / ROWS_PER_PAGE;

    for(uint32_t i = 0; i < num_full_pages; i++) {
        if(pager->pages[i] == NULL) {
            continue;
        }
        pager_flush(pager, i, PAGE_SIZE);
        free(pager->pages[i]);
        pager->pages[i] = NULL;
    }

    uint32_t num_additional_rows = table->num_rows % ROWS_PER_PAGE;
    if(num_additional_rows > 0) {
        uint32_t page_num = num_full_pages;
        if(pager->pages[page_num] != NULL) {
            pager_flush(pager, page_num, num_additional_rows * ROW_SIZE);
            free(pager->pages[page_num]);
            pager->pages[page_num] = NULL;
        }
    }

    int result = close(pager->file_descriptor);
    if(result == -1) {
        printf("Error closing db file.\n");
        exit(EXIT_FAILURE);
    }
    for(uint32_t i = 0; i < TABLE_MAX_PAGES; i++) {
        void* page = pager->pages[i];
        if(page) {
            free(page);
            pager->pages[i] = NULL;
        }
    }
    free(pager);
    free(table);
}

MetaCommandResult do_mata_command(InputBuffer* input_buffer, Table* table) {
    if(strcmp(input_buffer->buffer, ".exit") == 0) {
        close_input_buffer(input_buffer);       
        db_close(table);      
        exit(EXIT_SUCCESS);
    } else {
        return META_COMMAND_UNRECOGNIZED_COMMAND;
    }
}
```

在我们当前的设计中，文件的长度决定数据库中的行数，因此我们需要在文件的末尾写一个不完整的页面。这就是 `pager_flush()` 需要同时接受页码和大小的原因。这不是一个好设计，但当我们实现B树时就不再需要它。

```c
void pager_flush(Pager* pager, uint32_t page_num, uint32_t size) {
    if(pager->pages[page_num] == NULL) {
        printf("Tried to flush null page\n");
        exit(EXIT_FAILURE);
    }

    off_t offset = lseek(pager->file_descriptor, page_num * PAGE_SIZE, SEEK_SET);

    if(offset == -1) {
        printf("Error seeking %d\n", errno);
        exit(EXIT_FAILURE);
    }

    ssize_t bytes_written = write(pager->file_descriptor, pager->pages[page_num], size);

    if(bytes_written == -1) {
        printf("Error writing: %d\n", errno);
        exit(EXIT_FAILURE);
    }
}
```

最后，我们需要接受文件名作为命令行参数。不要忘了在`do_meta_command` 中添加额外的参数：

```c
int main(int argc, char* argv[]) {
    if(argc < 2) {
        printf("Must supply a database filename.\n");
        exit(EXIT_FAILURE);
    }

    char* filename = argv[1];
    Table* table = db_open(filename);


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
        ...
    }
    ...
}
```

通过这些更改，我们关闭然后重新打开数据库，记录仍然存在！

```
$ ./db mydb.db
db > insert 1 cstack foo@bar.com
Executed.
db > insert 2 voltorb volty@example.com
Executed.
db > .exit
~
$ ./db mydb.db
db > select
(1, cstack, foo@bar.com)
(2, voltorb, volty@example.com)
Executed.
db > .exit

```


为了增加乐趣，让我们打开 mydb.db 来查看我们的数据是如何存储的。我将使用 vim 作为十六进制编辑器来查看文件的内存布局：

```
vim mydb.db
:%!xxd
```

![Current File Format](/img/file-format.png)

前四个字节是第一行的id（因为我们用了 uint32_t 所以是4字节）。它以小端字节顺序存储，因此最低有效字节排在第一位（01），然后是高位字节（00）。我们使用 `memcpy()` 将行结构中的字节复制到页面缓存中，这意味着该结构以小端字节顺序排列在内存中。这是我编译程序的机器的一个属性。如果我们想在我的机器上写一个数据库文件，然后在大端机器上读取它，那么我们必须将 `serialize_row()` 和 `deserialize_row()` 方法更改为始终以相同的顺序存储和读取字节。

接下来的33个字节将用户名存储为以 null 结尾的字符串。显然，ASCII十六进制中的“cstack”是63 73 74 61 6b，后跟一个 null 字符（00）。其余33个字节未使用。

接下来的256个字节以相同的方式存储电子邮件。在这里，我们可以看到终止 null 字符后的一些随机垃圾字符。这很可能是因为行结构中的内存未初始化。我们将整个256字节的电子邮件缓冲区复制到文件中，包括字符串结束后的字节。当我们分配该结构时，内存中的内容仍然存在。但由于我们使用了终止的 null 字符，后边的垃圾字符不会对行为产生影响。

**注意**：如果我们想确保所有字节都已初始化，那么在`serialize_row` 中复制行的用户名和电子邮件字段时，使用 `strncpy` 替换 `memcpy`就行了，例如：

```c
void serialize_row(Row *source, void* destination) {
    memcpy(destination + ID_OFFSET, &(source->id), ID_SIZE);
    strncpy(destination + USERNAME_OFFSET, &(source->username), USERNAME_SIZE);
    strncpy(destination + EMAIL_OFFSET, &(source->email), EMAIL_SIZE);
}
```

## 总结

我们实现了持久化。我们还有进步空间。例如，如果您你没有键入 `.exit` 的情况下终止程序，则会丢失所做的更改。此外，我们会将所有页面写回磁盘，即使自我们从磁盘读取后未更改任何页面。这些是我们稍后要解决的问题。

下一次我们将介绍游标，它能让我么能更加方便地实现B树。



