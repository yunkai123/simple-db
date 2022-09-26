# 第9部分-二分查找和重复键

上一部分我们注意到，我们仍然未按排序顺序存储键。我们将解决这个问题，并检测和拒绝重复键。

现在，我们的 `execute_insert()` 函数总是选择在表的末尾插入。相反，我们应该在表中查找要插入的正确位置，然后在那里插入。如果键已存在，则返回错误。

```c
ExecuteResult execute_insert(Statement* statement, Table* table) {
    void* node = get_page(table->pager, table->root_page_num);

    uint32_t num_cells = (*leaf_node_num_cells(node));
    if((num_cells == LEAF_NODE_MAX_CELLS)) {
        return EXECUTE_TABLE_FULL;
    }

    Row* row_to_insert = &(statement->row_to_insert);
    uint32_t key_to_insert = row_to_insert->id;
    Cursor* cursor = table_find(table, key_to_insert);

    if(cursor->cell_num < num_cells) {
        uint32_t key_at_index = *leaf_node_key(node, cursor->cell_num);
        if(key_at_index == key_to_insert) {
            return EXECUTE_DUPLICATE_KEY;
        }
    }

    leaf_node_insert(cursor, row_to_insert->id, row_to_insert);
    ...
}
```

我们不再需要 `table_end()` 函数。我们将用一个在树中查找给定键的方法替换它。

```c
/*
 * Return the position of the given key.
 * If the key is not present, return the position
 * where it should be inserted
 */
Cursor* table_find(Table* table, uint32_t key) {
    uint32_t root_page_num = table->root_page_num;
    void* root_node = get_page(table->pager, root_page_num);

    if(get_node_type(root_node) == NODE_LEAF) {
        return leaf_node_find(table, root_page_num, key);
    } else {
        printf("Need to implement searching an internal node\n");
        exit(EXIT_FAILURE);
    }
}
```

我剔除了内部节点的分支，因为我们还没有实现内部节点。我们可以用二分查找来搜索叶子节点。

```c
Cursor* leaf_node_find(Table* table, uint32_t page_num, uint32_t key) {
    void* node = get_page(table->pager, page_num);
    uint32_t num_cells = *leaf_node_num_cells(node);

    Cursor* cursor = malloc(sizeof(cursor));
    cursor->table = table;
    cursor->page_num = page_num;

    // Binary search
    uint32_t min_index =0 ;
    uint32_t one_past_max_index = num_cells;
    while(one_past_max_index != min_index) {
        uint32_t index = (min_index + one_past_max_index) / 2;
        uint32_t key_at_index = *leaf_node_key(node, index);
        if(key == key_at_index) {
            cursor->cell_num = index;
            return cursor;
        }
        if(key < key_at_index) {
            one_past_max_index = index;
        } else {
            min_index = index + 1;
        }
    }

    cursor->cell_num = min_index;
    return cursor;
}
```

它会返回：

- 键的位置，
- 如果要插入新键，需要移动的另一个键的位置，或者
- 最后一个键后边的位置

我们现在要检查节点类型，所以需要函数来获取和设置节点的类型。

```c
NodeType get_node_type(void* node) {
    uint8_t value = *((uint8_t*)(node + NODE_TYPE_OFFSET));
    return (NodeType)value;
}

void set_node_type(void* node, NodeType type) {
    uint8_t value = type;
    *((uint8_t*)(node + NODE_TYPE_OFFSET)) = value;
}
```

我们必须首先转换为 `uint8_ t`，以确保将其序列化为单个字节。

我们还需要初始化节点类型。

```c
void initialize_leaf_node(void* node) {
    set_node_type(node, NODE_LEAF);
    *leaf_node_num_cells(node) = 0;
}
```

最后，我们需要生成并处理一个新的错误码。

```c
typedef enum {
    EXECUTE_SUCCESS,
    EXECUTE_TABLE_FULL,
    EXECUTE_DUPLICATE_KEY
} ExecuteResult;
```

```c
        switch(execute_statement(&statement, table)) {
            case (EXECUTE_SUCCESS):
                printf("Executed.\n");
                break;
            case (EXECUTE_DUPLICATE_KEY):
                printf("Error: Duplicate key.\n");
                break;
            case (EXECUTE_TABLE_FULL):
                printf("Error: Table full.\n");
                break;
        }
```

通过这些更改，我们的测试用例可以更改为检查排序顺序：

```py
    def test_print_one_node_bt_structure(self):
        ...

        assert results == [
            ...,
            "leaf (size 3)",
            " - 0 : 1",
            " - 1 : 2",
            " - 2 : 3",
            "db > "
        ]
```

我们可以为重复键添加新的测试：

```py
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
```


就这样！下一步：实现拆分叶节点和创建内部节点。





