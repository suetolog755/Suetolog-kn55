import os
import math
import argparse
import datetime
import struct
import numpy as np

def cli():
    parser = argparse.ArgumentParser(description="Convert .kn5 models to .obj")
    parser.add_argument("path", help="Path to .kn5 file or directory with .kn5 files")
    args = parser.parse_args()
    target = os.path.abspath(args.path)

    if os.path.isfile(target) and target.endswith(".kn5"):
        convert_to_obj(target)
    elif os.path.isdir(target):
        for f in os.listdir(target):
            if f.endswith(".kn5"):
                convert_to_obj(os.path.join(target, f))
    else:
        print("Invalid path or no .kn5 files found")
        raise SystemExit(1)


class kn5Material:
    def __init__(self):
        self.name = ""
        self.shader = ""
        self.ksAmbient = 0.6
        self.ksDiffuse = 0.6
        self.ksSpecular = 0.9
        self.ksSpecularEXP = 1.0
        self.diffuseMult = 1.0
        self.useDetail = 0.0
        self.detailUVMultiplier = 1.0
        self.txDiffuse = ""
        self.txNormal = ""
        self.txDetail = ""
        self.txDetailR = ""
        self.txDetailG = ""
        self.txDetailB = ""
        self.txDetailA = ""
        self.txDetailNM = ""
        self.txMask = ""
        self.shader_props = ""
        self.ksEmissive = 0.0
        self.ksAlphaRef = 1.0


class kn5Node:
    def __init__(self):
        self.name = "Default"
        self.parent = None
        self.tmatrix = np.identity(4)
        self.hmatrix = np.identity(4)
        self.type = 1
        self.materialID = -1
        self.vertexCount = 0
        self.indices = []
        self.position = []
        self.normal = []
        self.texture0 = []


def read_string(file, length):
    return file.read(length).decode("utf-8")


def matrix_mult(ma, mb):
    return np.matmul(np.array(ma, copy=True), np.array(mb, copy=True))


def matrix_to_euler(transf):
    if transf[0][1] > 0.998:
        heading = np.arctan2(-transf[1][0], transf[1][1])
        attitude = -math.pi / 2
        bank = 0.0
    elif transf[0][1] < -0.998:
        heading = np.arctan2(-transf[1][0], transf[1][1])
        attitude = math.pi / 2
        bank = 0.0
    else:
        heading = np.arctan2(transf[0][1], transf[0][0])
        bank = np.arctan2(transf[1][2], transf[2][2])
        attitude = np.arcsin(-transf[0][2])
    return [bank * 180 / math.pi, attitude * 180 / math.pi, heading * 180 / math.pi]


def scale_from_matrix(transf):
    return [
        math.sqrt(transf[0][0]**2 + transf[1][0]**2 + transf[2][0]**2),
        math.sqrt(transf[0][1]**2 + transf[1][1]**2 + transf[2][1]**2),
        math.sqrt(transf[0][2]**2 + transf[1][2]**2 + transf[2][2]**2)
    ]


def read_nodes(file, node_list, parent_id):
    new_node = kn5Node()
    new_node.parent = parent_id
    new_node.type, = struct.unpack('<i', file.read(4))
    new_node.name = read_string(file, struct.unpack('<i', file.read(4))[0])
    children_count, = struct.unpack('<i', file.read(4))
    file.read(1)  # skip byte

    if new_node.type == 1:  # Dummy
        new_node.tmatrix = [[struct.unpack('<f', file.read(4))[0] for _ in range(4)] for _ in range(4)]
        new_node.translation = [new_node.tmatrix[3][0], new_node.tmatrix[3][1], new_node.tmatrix[3][2]]
        new_node.rotation = matrix_to_euler(new_node.tmatrix)
        new_node.scaling = scale_from_matrix(new_node.tmatrix)

    elif new_node.type == 2:  # Static mesh
        file.read(3)  # skip bytes
        new_node.vertexCount, = struct.unpack('<i', file.read(4))
        for _ in range(new_node.vertexCount):
            new_node.position.extend(struct.unpack('<fff', file.read(12)))
            new_node.normal.extend(struct.unpack('<fff', file.read(12)))
            tex = struct.unpack('<ff', file.read(8))
            new_node.texture0.extend([tex[0], 1.0 - tex[1]])
            file.read(12)  # tangents
        index_count, = struct.unpack('<i', file.read(4))
        new_node.indices = struct.unpack('<%dH' % index_count, file.read(index_count * 2))
        new_node.materialID, = struct.unpack('<i', file.read(4))
        file.read(29)  # skip bytes

    elif new_node.type == 3:  # Animated mesh
        file.read(3)
        bone_count, = struct.unpack('<i', file.read(4))
        for _ in range(bone_count):
            _ = read_string(file, struct.unpack('<i', file.read(4))[0])
            file.read(64)  # bone matrix
        new_node.vertexCount, = struct.unpack('<i', file.read(4))
        for _ in range(new_node.vertexCount):
            new_node.position.extend(struct.unpack('<fff', file.read(12)))
            new_node.normal.extend(struct.unpack('<fff', file.read(12)))
            tex = struct.unpack('<ff', file.read(8))
            new_node.texture0.extend([tex[0], 1.0 - tex[1]])
            file.read(44)  # tangents & weights
        index_count, = struct.unpack('<i', file.read(4))
        new_node.indices = struct.unpack('<%dH' % index_count, file.read(index_count * 2))
        new_node.materialID, = struct.unpack('<i', file.read(4))
        file.read(12)

    new_node.hmatrix = new_node.tmatrix if parent_id < 0 else matrix_mult(new_node.tmatrix, node_list[parent_id].hmatrix)
    node_list.append(new_node)
    current_id = len(node_list) - 1

    for _ in range(children_count):
        node_list = read_nodes(file, node_list, current_id)
    return node_list


def transparant_shader(shader):
    return shader.startswith("ksPerPixelAT") or shader in ['ksPerPixelAlpha', 'ksSkidMark', 'ksTree', 'ksGrass', 'ksFlags']


def export_obj(model_name, output_dir, materials, nodes):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Write MTL
    with open(os.path.join(output_dir, model_name + '.mtl'), 'w') as f:
        for mat in materials:
            f.write(f'newmtl {mat.name.replace(" ", "_")}\r\n')
            f.write(f'Ka {mat.ksAmbient} {mat.ksAmbient} {mat.ksAmbient}\r\n')
            f.write(f'Kd {mat.ksDiffuse} {mat.ksDiffuse} {mat.ksDiffuse}\r\n')
            f.write(f'Ks {mat.ksSpecular} {mat.ksSpecular} {mat.ksSpecular}\r\n')
            f.write(f'Ns {mat.ksSpecularEXP}\r\n')
            f.write('illum 2\r\n')
            is_transp = transparant_shader(mat.shader)
            if is_transp:
                f.write('d 0.9999\r\n')
            if mat.useDetail == 1.0 and mat.txDetail:
                f.write(f'map_Kd texture\\{mat.txDetail}\r\n')
                if mat.txDiffuse:
                    f.write(f'map_Ks texture\\{mat.txDiffuse}\r\n')
                if is_transp:
                    f.write(f'map_d texture\\{mat.txDetailA}\r\n')
            elif mat.txDiffuse:
                f.write(f'map_Kd texture\\{mat.txDiffuse}\r\n')
                if is_transp:
                    f.write(f'map_d texture\\{mat.txDiffuse}\r\n')
            if mat.txNormal:
                f.write(f'bump texture\\{mat.txNormal}\r\n')
            f.write('\r\n')

    # Write OBJ
    with open(os.path.join(output_dir, model_name + ".obj"), "w") as f:
        f.write(f"# Assetto Corsa model\n# Exported on {datetime.datetime.now()}\n\nmtllib {model_name}.mtl\n")
        vertex_pad = 1

        for node in nodes:
            if node.name.startswith("AC_") or node.type == 1:
                continue
            if node.type in [2, 3]:
                f.write(f"\ng {node.name.replace(' ', '_')}\n")
                # Vertices
                for v in range(node.vertexCount):
                    x, y, z = node.position[v*3:v*3+3]
                    h = node.hmatrix
                    vx = h[0][0]*x + h[1][0]*y + h[2][0]*z + h[3][0]
                    vy = h[0][1]*x + h[1][1]*y + h[2][1]*z + h[3][1]
                    vz = h[0][2]*x + h[1][2]*y + h[2][2]*z + h[3][2]
                    f.write(f"v {vx} {vy} {vz}\n")
                # Normals
                for v in range(node.vertexCount):
                    x, y, z = node.normal[v*3:v*3+3]
                    h = node.hmatrix
                    nx = h[0][0]*x + h[1][0]*y + h[2][0]*z
                    ny = h[0][1]*x + h[1][1]*y + h[2][1]*z
                    nz = h[0][2]*x + h[1][2]*y + h[2][2]*z
                    f.write(f"vn {nx} {ny} {nz}\n")
                # UVs
                uv_mult = 1.0
                if node.materialID >= 0:
                    mat = materials[node.materialID]
                    uv_mult = mat.detailUVMultiplier if mat.useDetail == 1.0 else mat.diffuseMult
                for v in range(node.vertexCount):
                    tx, ty = node.texture0[v*2]*uv_mult, node.texture0[v*2+1]*uv_mult
                    f.write(f"vt {tx} {ty}\n")
                # Faces
                if node.materialID >= 0:
                    f.write(f"\r\nusemtl {materials[node.materialID].name.replace(' ', '_')}\r\n")
                else:
                    f.write("\r\nusemtl Default\r\n")
                for i in range(0, len(node.indices), 3):
                    i1, i2, i3 = node.indices[i]+vertex_pad, node.indices[i+1]+vertex_pad, node.indices[i+2]+vertex_pad
                    f.write(f"f {i1}/{i1}/{i1} {i2}/{i2}/{i2} {i3}/{i3}/{i3}\r\n")
                vertex_pad += node.vertexCount


def read_kn5(file_path, output_dir):
    with open(file_path, "rb") as file:
        header = file.read(10)
        _, version = struct.unpack("<6s1I", header)
        if version > 5:
            file.read(4)

        # Textures
        tex_count, = struct.unpack("<i", file.read(4))
        for _ in range(tex_count):
            tex_type, = struct.unpack("<i", file.read(4))
            tex_name = read_string(file, struct.unpack("<i", file.read(4))[0])
            tex_size, = struct.unpack("<i", file.read(4))
            tex_path = os.path.join(output_dir, "texture", tex_name)
            if not os.path.exists(tex_path):
                os.makedirs(os.path.dirname(tex_path), exist_ok=True)
                with open(tex_path, "wb") as tf:
                    tf.write(file.read(tex_size))
            else:
                file.seek(tex_size, 1)

        # Materials
        mat_count, = struct.unpack("<i", file.read(4))
        materials = []
        for _ in range(mat_count):
            mat = kn5Material()
            mat.name = read_string(file, struct.unpack("<i", file.read(4))[0])
            mat.shader = read_string(file, struct.unpack("<i", file.read(4))[0])
            file.read(2)  # ashort
            if version > 4:
                file.read(4)
            prop_count, = struct.unpack("<i", file.read(4))
            for _ in range(prop_count):
                prop_name = read_string(file, struct.unpack("<i", file.read(4))[0])
                prop_value, = struct.unpack("<f", file.read(4))
                mat.shader_props += f"{prop_name} = {prop_value}&cr;&lf;"
                if prop_name == "ksAmbient": mat.ksAmbient = prop_value
                elif prop_name == "ksDiffuse": mat.ksDiffuse = prop_value
                elif prop_name == "ksSpecular": mat.ksSpecular = prop_value
                elif prop_name == "ksSpecularEXP": mat.ksSpecularEXP = prop_value
                elif prop_name == "diffuseMult": mat.diffuseMult = prop_value
                elif prop_name == "useDetail": mat.useDetail = prop_value
                elif prop_name == "detailUVMultiplier": mat.detailUVMultiplier = prop_value
                elif prop_name == "ksEmissive": mat.ksEmissive = prop_value
                elif prop_name == "ksAlphaRef": mat.ksAlphaRef = prop_value
                file.read(36)
            tex_count2, = struct.unpack("<i", file.read(4))
            for _ in range(tex_count2):
                sample_name = read_string(file, struct.unpack("<i", file.read(4))[0])
                sample_slot, = struct.unpack("<i", file.read(4))
                tex_name = read_string(file, struct.unpack("<i", file.read(4))[0])
                mat.shader_props += f"{sample_name} = {tex_name}&cr;&lf;"
                if sample_name == "txDiffuse": mat.txDiffuse = tex_name
                elif sample_name == "txNormal": mat.txNormal = tex_name
                elif sample_name == "txDetail": mat.txDetail = tex_name
                elif sample_name == "txDetailR": mat.txDetailR = tex_name
                elif sample_name == "txDetailG": mat.txDetailG = tex_name
                elif sample_name == "txDetailB": mat.txDetailB = tex_name
                elif sample_name == "txDetailA": mat.txDetailA = tex_name
                elif sample_name == "txDetailNM": mat.txDetailNM = tex_name
                elif sample_name == "txMask": mat.txMask = tex_name
            materials.append(mat)

        # Nodes
        nodes = read_nodes(file, [], -1)

    return materials, nodes


def convert_to_obj(file_path):
    model_name = os.path.splitext(os.path.basename(file_path))[0]
    output_dir = os.path.join(os.path.dirname(file_path), "output")
    materials, nodes = read_kn5(file_path, output_dir)
    export_obj(model_name, output_dir, materials, nodes)
    print(f"Converted: {model_name}")


if __name__ == "__main__":
    cli()
