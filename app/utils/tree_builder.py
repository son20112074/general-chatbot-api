
def make_tree(data_list):
        
        
        ID  = 'id'
        KEY  = 'parent_path'
        for data in data_list:
            if data['parent_path'] == None:
                data['parent_path'] = ''
            data[ID] = str(data[ID])
            data['expanded'] = True
            data['isLeaf'] = True

   
        sorted_list = sorted(data_list, key=lambda k: k[KEY])

        node_map = {}
        for elem in  sorted_list:
            elem['children'] = []
            node_map[elem[ID]] = elem 

        for elem in sorted_list:
            parent_path = elem[KEY]

            try:            
                parent_id = parent_path.split(',')[-2]
                if (parent_id != ""):
                    node_map[parent_id]['children'].append(elem)
                    node_map[parent_id]['isLeaf'] = False
            except:
                elem[KEY] = ''
        
        return [elem for elem in sorted_list if elem[KEY] == '']

def make_tree_role(data_list):
        ID  = 'id'
        KEY  = 'parent_path'
        for data in data_list:
            if data['parent_path'] == None:
                data['parent_path'] = ''
            data[ID] = str(data[ID])
            data['expanded'] = True
            data['isLeaf'] = True

        sorted_list = sorted(data_list, key=lambda k: k[KEY])
        
        node_map = {}
        for elem in  sorted_list:
            elem['children'] = []
            node_map[elem[ID]] = elem 

        for elem in sorted_list:
            parent_path = elem[KEY]

            try:            
                parent_id = parent_path.split(',')[-2]
                if (parent_id != ""):
                    node_map[parent_id]['children'].append(elem)
                    node_map[parent_id]['isLeaf'] = False
            except:
                elem[KEY] = ''

        return [elem for elem in sorted_list if elem[KEY] == '']

def make_tree_flat(data_list):
        ID  = 'id'
        KEY  = 'parent_path'
        for data in data_list:
            if data.get('parent_path', None) == None:
                data['parent_path'] = ''
            data[ID] = str(data[ID])
            data['expanded'] = True
            data['isLeaf'] = True
                
        sorted_list = sorted(data_list, key=lambda k: k[KEY])
        
        node_map = {}
        for elem in  sorted_list:
            elem['children'] = []
            node_map[elem[ID]] = elem 

        for elem in sorted_list:
            parent_path = elem[KEY]

            try:            
                parent_id = parent_path.split(',')[-2]
                if (parent_id != ""):
                    node_map[parent_id]['children'].append(elem)
                    node_map[parent_id]['isLeaf'] = False
            except:
                elem[KEY] = ''
                
        ct_tree = [elem for elem in sorted_list if elem[KEY] == '']
        return flat_tree(add_stt(ct_tree[::-1], ''))

def add_stt(ct_list, base_stt):
    for idx in range(len(ct_list)):
        ct_list[idx]['stt'] = '{}{}.'.format(base_stt, str(idx+1))
        if len(ct_list[idx]['children']) > 0:
            add_stt(ct_list[idx]['children'], '{}{}.'.format(base_stt, str(idx+1)))
    return ct_list


def flat_tree(ct_tree):
    flat = []
    for ct in ct_tree:
        new = []
        if len(ct['children']) > 0:
            new = flat_tree(ct['children'])
        ct['children'] = []
        count = len(ct['stt'].split('.'))

        flat.append(ct)
        if len(new) > 0:
            flat.extend(new)
    
    return flat
