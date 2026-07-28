# 2026-07-12T13:36:07.181761500
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.build()

comp = client.get_component(name="lwip_echo_server")
comp.build()

status = platform.build()

comp.build()

vitis.dispose()

