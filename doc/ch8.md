# 第8部分-B树叶节点格式

我们正在将表的格式从未排序的行数组更改为B树。这是一个相当大的变化，需要多篇文章才能实现。在本文结束时，我们将定义叶子节点的布局，并支持将键/值对插入到单个节点树中。但首先，让我们回顾一下切换到树结构的原因。

## 可选的表结构

在当前格式下，每个页面只存储行（没有元数据），因此非常节省空间。插入也很快，因为我们只是在末尾追加。但是，只能通过扫描整个表来查找特定行。如果我们想删除一行，我们必须移动它后面的每一行来填补这个洞。

如果我们将表存储为一个数组，并按id对行进行排序，我们可以使用二分搜索来查找特定id。然而，插入速度会很慢，因为我们必须移动很多行才能腾出空间。

因此，我们将使用树结构。树中的每个节点可以包含可变数量的行，因此我们必须在每个节点中存储一些信息，以追踪它包含多少行。此外，还有不存储任何行的内部节点的存储开销。作为交换，在一个大数据库文件中，我们可以快速插入、删除和查找。

|未排序行数组|排序行数组|节点树|
|-|-|-|
|页面包含|仅数据|仅数据|元数据、主键和数据|
|每页的行|多|多|少|
|插入|O(1)|O(1)|O(log(n))|
|删除|O(n)|O(n)|O(log(n))|
|根据id查找|O(n)|O(log(n))|O(log(n))|

## 节点头部格式

叶子节点和内部节点具有不同的布局。让我们制作一个枚举来跟踪节点类型：


每个节点对应一个页面。内部节点将通过存储子节点的页码来指向其子节点。B树向页面处理器请求特定的页码，并将指针返回到页面缓存中。页面按页码顺序依次存储在数据库文件中。

节点需要在页面开头的头部中存储一些元数据。每个节点将存储它是什么类型的节点，无论它是否是根节点，以及指向其父节点的指针（以允许查找节点的同级节点）。我为每个头部字段的大小和偏移量定义常量：

```c
/*
 * Common Node Header Layout
 */
const uint32_t NODE_TYPE_SIZE = sizeof(uint8_t);
const uint32_t NODE_TYPE_OFFSET = 0;
const uint32_t IS_ROOT_SIZE = sizeof(uint8_t);
const uint32_t IS_ROOT_OFFSET = NODE_TYPE_SIZE;
const uint32_t PARENT_POINTER_SIZE = sizeof(uint32_t);
const uint32_t PARENT_POINTER_OFFSET = IS_ROOT_OFFSET + IS_ROOT_SIZE;
const uint8_t COMMON_NODE_HEADER_SIZE =
    NODE_TYPE_SIZE + IS_ROOT_SIZE + PARENT_POINTER_SIZE;
```

## 叶子节点格式

除了这些常见的头部字段外，叶子节点还需要存储它们包含的“单元格”数量。单元格是键/值对。

```c
/*
 * Leaf Node Header Layout
 */
const uint32_t LEAF_NODE_NUM_CELLS_SIZE = sizeof(uint32_t);
const uint32_t LEAF_NODE_NUM_CELLS_OFFSET = COMMON_NODE_HEADER_SIZE;
const uint32_t LEAF_NODE_HEADER_SIZE =
    COMMON_NODE_HEADER_SIZE + LEAF_NODE_NUM_CELLS_SIZE;
```

叶子节点的主体是一个单元格数组。每个单元格是一个键后跟一个值（序列化的行）。

```c
/*
 * Leaf Node Body Layout
 */
const uint32_t LEAF_NODE_KEY_SIZE = sizeof(uint32_t);
const uint32_t LEAF_NODE_KEY_OFFSET = 0;
const uint32_t LEAF_NODE_VALUE_SIZE = ROW_SIZE;
const uint32_t LEAF_NODE_VALUE_OFFSET =
    LEAF_NODE_KEY_OFFSET + LEAF_NODE_KEY_SIZE;
const uint32_t LEAF_NODE_CELL_SIZE = LEAF_NODE_KEY_SIZE + LEAF_NODE_VALUE_SIZE;
const uint32_t LEAF_NODE_SPACE_FOR_CELLS = PAGE_SIZE - LEAF_NODE_HEADER_SIZE;
const uint32_t LEAF_NODE_MAX_CELLS =
    LEAF_NODE_SPACE_FOR_CELLS / LEAF_NODE_CELL_SIZE;
```

基于这些常量，以下是叶子节点当前的布局：

![](/img/leaf-node-format.png)

在头部每个布尔值使用一个完整的字节会有一点浪费空间，但这使得编写代码来访问这些值变得更容易。

还要注意的是，在结尾浪费了一些空间。我们在头部后存储尽可能多的单元格，但剩余空间无法容纳整个单元格。我们将其留空，以避免在节点之间拆分单元格。

## 访问叶子节点字段

访问键、值和元数据的代码都涉及使用我们刚刚定义的常量的指针算法。

```c
uint32_t* leaf_node_num_cells(void* node) {
    return node + LEAF_NODE_NUM_CELLS_OFFSET;
}

void* leaf_node_cell(void* node, uint32_t cell_num) {
    return node + LEAF_NODE_HEADER_SIZE + cell_num * LEAF_NODE_CELL_SIZE;
}

uint32_t* leaf_node_key(void* node, uint32_t cell_num) {
    return leaf_node_cell(node, cell_num);
}

void* leaf_node_value(void* node, uint32_t cell_num) {
    return leaf_node_cell(node, cell_num) + LEAF_NODE_KEY_SIZE;
}

void initialize_leaf_node(void* node) {
    *leaf_node_num_cells(node) = 0;
}
```

这些方法返回指向问题中的值的指针，因此它们既可以用作getter，也可以用作setter。

## Pager 和 Table 的修改

每个节点将占用一个页面，即使它没有满。这意味着我们的页面处理器不再需要支持读/写部分页面。

```c
void pager_flush(Pager* pager, uint32_t page_num) {  
    ...

    ssize_t bytes_written = write(pager->file_descriptor, pager->pages[page_num], PAGE_SIZE);

    ...
}
```

```c
void db_close(Table* table) {
    Pager* pager = table->pager;

    for(uint32_t i = 0; i < pager->num_pages; i++) {
        if(pager->pages[i] == NULL) {
            continue;
        }
        pager_flush(pager, i);
        free(pager->pages[i]);
        pager->pages[i] = NULL;
    }

    int result = close(pager->file_descriptor);
    ...
}

```

现在，存储数据库中的页数比存储行数更有意义。页数应该与页面处理器对象相关联，而不是与表相关联，因为它是数据库使用的页数，而不是特定的表。B树由其根节点页码标识，因此表对象需要跟踪该页码。

```c
const uint32_t PAGE_SIZE = 4096;
#define TABLE_MAX_PAGES 100

typedef struct {
    int file_descriptor;
    uint32_t file_length;
    uint32_t num_pages;
    void* pages[TABLE_MAX_PAGES];
} Pager;

typedef struct {
    uint32_t root_page_num;
    Pager* pager;
} Table;
```

```c
void* get_page(Pager* pager, uint32_t page_num) {
    ...

    if(pager->pages[page_num] == NULL) {
        ...

        pager->pages[page_num] = page;

        if(page_num >= pager->num_pages) {
            pager->num_pages = page_num + 1;
        }
    }

    return pager->pages[page_num];
}
```

```c
Pager* pager_open(const char* filename) {
    ...

    Pager* pager = malloc(sizeof(Pager));
    pager->file_descriptor = fd;
    pager->file_length = file_length;
    pager->num_pages = (file_length / PAGE_SIZE);

    if(file_length % PAGE_SIZE != 0) {
        printf("Db file is not a whole number of page. Corrupt file.\n");
        exit(EXIT_FAILURE);
    }

    for(uint32_t i = 0; i < TABLE_MAX_PAGES; i++) {
        pager->pages[i] = NULL;
    }
    return pager;
}
```

## 对 Cursor 对象的更改

游标表示表中的一个位置。当我们的表是一个简单的行数组时，我们可以仅通过行号访问给定行。现在它是一棵树，我们通过节点的页码和节点内的单元号来标识位置。

```c
typedef struct {
    Table* table;
    uint32_t page_num;
    uint32_t cell_num;
    bool end_of_table; // Indicates a position one past the last element
} Cursor;
```

```c
Cursor* table_start(Table* table) {
    Cursor* cursor = malloc(sizeof(Cursor));
    cursor->table = table;
    cursor->page_num = table->root_page_num;
    cursor->cell_num = 0;

    void* root_node = get_page(table->pager, table->root_page_num);
    uint32_t  num_cells = *leaf_node_num_cells(root_node);
    cursor->end_of_table = (num_cells == 0);

    return cursor;
}
```

```c
Cursor* table_end(Table* table) {
    Cursor* cursor = malloc(sizeof(cursor));
    cursor->table = table;
    cursor->page_num = table->root_page_num;

    void* root_node = get_page(table->pager, table->root_page_num);
    uint32_t num_cells = *leaf_node_num_cells(root_node);
    cursor->cell_num = num_cells;

    cursor->end_of_table = true;

    return cursor;
}
```

```c
void* cursor_value(Cursor* cursor) {
    uint32_t page_num = cursor->page_num;
    void *page = get_page(cursor->table->pager, page_num);  
    return leaf_node_value(page, cursor->cell_num);
}
```

```c
void cursor_advance(Cursor* cursor) {
    uint32_t page_num = cursor->page_num;
    void* node = get_page(cursor->table->pager, page_num);

    cursor->cell_num += 1;
    if(cursor->cell_num >= (*leaf_node_num_cells(node))) {
        cursor->end_of_table = true;
    }
}
```

## 插入到叶子节点中

在本文中，我们将只实现单节点树。回想上一篇文章，树从一个空叶子节点开始：

![](/img/empty_btree.png)

可以添加键/值对，直到叶子节点已满：

![](/img/one-node-btree.png)

当我们第一次打开数据库时，数据库文件为空，因此我们将页面0初始化为空叶子节点（根节点）：

```c
Table* db_open(const char* filename) {
    Pager* pager = pager_open(filename);

    Table* table = malloc(sizeof(Table));
    table->pager = pager;
    table->root_page_num = 0;

    if(pager->num_pages == 0) {
        // New database file. Initialize page 0 as leaf node
        void* root_node = get_page(pager, 0);
        initialize_leaf_node(root_node);
    }

    return table;
}
```


接下来，我们将创建一个函数，用于将键/值对插入叶子节点。它将以一个游标作为输入，以表示该对应插入的位置。

```c
void leaf_node_insert(Cursor* cursor, uint32_t key, Row* value) {
    void* node = get_page(cursor->table->pager, cursor->page_num);

    uint32_t num_cells = *leaf_node_num_cells(node);
    if(num_cells >= LEAF_NODE_MAX_CELLS) {
        // Node full
        printf("Need to implement splitting a leaf node.\n");
        exit(EXIT_FAILURE);
    }

    if(cursor->cell_num < num_cells) {
        // Make room for new cell
        for(uint32_t i = num_cells; i > cursor->cell_num; i--) {
            memcpy(leaf_node_cell(node, i), leaf_node_cell(node, i - 1), LEAF_NODE_CELL_SIZE);
        }
    }

    *(leaf_node_num_cells(node)) += 1;
    *(leaf_node_key(node, cursor->cell_num)) = key;
    serialize_row(value, leaf_node_value(node, cursor->cell_num));
}
```


我们还没有实现拆分，因此如果节点已满，就会报错。接下来，我们将单元格向右移动一个空间，为新单元格腾出空间。然后我们将新的键/值写入空白空间。

由于我们假设树只有一个节点，我们的 `execute_insert()` 函数只需要调用这个辅助方法：

```c
ExecuteResult execute_insert(Statement* statement, Table* table) {
    void* node = get_page(table->pager, table->root_page_num);

    if((*leaf_node_num_cells(node) == LEAF_NODE_MAX_CELLS)) {
        return EXECUTE_TABLE_FULL;
    }

    Row* row_to_insert = &(statement->row_to_insert);
    Cursor* cursor = table_end(table);

    leaf_node_insert(cursor, row_to_insert->id, row_to_insert);

    free(cursor);

    return EXECUTE_SUCCESS;
}
```

有了这些变化，我们的数据库应该可以像以前一样工作！除了现在它会更快地返回“Table Full”错误，因为我们还不能拆分根节点。

叶子节点可以容纳多少行？

## 打印常量的命令

我添加了一个新的元命令来打印出一些感兴趣的常量。

```c
void print_constants() {
    printf("ROW_SIZE: %d\n", ROW_SIZE);
    printf("COMMON_NODE_HEADER_SIZE: %d\n", COMMON_NODE_HEADER_SIZE);
    printf("LEAF_NODE_HEADER_SIZE: %d\n", LEAF_NODE_HEADER_SIZE);
    printf("LEAF_NODE_CELL_SIZE: %d\n", LEAF_NODE_CELL_SIZE);
    printf("LEAF_NODE_SPACE_FOR_CELLS: %d\n", LEAF_NODE_SPACE_FOR_CELLS);
    printf("LEAF_NODE_MAX_CELLS: %d\n", LEAF_NODE_MAX_CELLS);
}
```

```c
MetaCommandResult do_mata_command(InputBuffer* input_buffer, Table* table) {
    if(strcmp(input_buffer->buffer, ".exit") == 0) {
        close_input_buffer(input_buffer);       
        db_close(table);      
        exit(EXIT_SUCCESS);
    } else if(strcmp(input_buffer->buffer, ".constants") == 0) {
        printf("Constants:\n");
        print_constants();
        return META_COMMAND_SUCCESS;
    } 
    ...
}
```

我还添加了一个测试用例，这样当这些常量发生变化时，我们会收到告警：

```py
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
            "LEAF_NODE_HEADER_SIZE: 10",
            "LEAF_NODE_CELL_SIZE: 297",
            "LEAF_NODE_SPACE_FOR_CELLS: 4086",
            "LEAF_NODE_MAX_CELLS: 13",
            "db > ",
        ]
```

所以我们的表现在可以容纳13行！

## 树可视化

为了帮助调试和可视化，我还添加了一个元命令来打印出B树的形象表示。

```c
void print_leaf_node(void* node) {
    uint32_t num_cells = *leaf_node_num_cells(node);
    printf("leaf (size %d)\n", num_cells);
    for(uint32_t i = 0; i < num_cells; i++) {
        uint32_t key = *leaf_node_key(node, i);
        printf(" - %d : %d\n", i, key);
    }
}
```

```c
MetaCommandResult do_mata_command(InputBuffer* input_buffer, Table* table) {
    ...
    else if(strcmp(input_buffer->buffer, ".btree") == 0) {
        printf("Tree:\n");
        print_leaf_node(get_page(table->pager, 0));
        return META_COMMAND_SUCCESS;
    }
    ...
}
```

还有一个测试用例：

```py
    def test_print_one_node_bt_structure(self):
        script = []
        arr = [3, 1, 2]
        for i in arr:
            script.append("insert {} user{} person{}@example.com".format(i, i, i))
        script.append(".btree")
        script.append(".exit")
        result = self.run_script(script)

        assert result == [
            "db > Executed.",
            "db > Executed.",
            "db > Executed.",
            "db > Tree:",
            "leaf (size 3)",
            " - 0 : 3",
            " - 1 : 1",
            " - 2 : 2",
            "db > "
        ]
```

哦，我们仍然没有按排序顺序存储行。你会注意到 `execute_insert()` 在`table_end()` 返回的位置插入叶子节点。因此，行是按插入顺序存储的，就像以前一样。

## 下一次

这一切似乎是倒退了一步。我们的数据库现在存储的行比以前少了，而且我们仍然按未排序的顺序存储行。但正如我在开始时所说，这是一个巨大的变化，将其分解为可管理的步骤非常重要。

下次，我们将实现按主键查找记录，并开始按排序顺序存储行。








