# 2026-03-17T00:58:09.639302100
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.build()

comp = client.get_component(name="lwip_echo_server")
status = comp.clean()

status = platform.build()

comp.build()

comp = client.get_component(name="mlp_app")
status = comp.clean()

comp = client.get_component(name="lwip_echo_server")
status = comp.clean()

status = platform.build()

comp = client.get_component(name="mlp_app")
comp.build()

status = comp.clean()

status = platform.build()

comp = client.get_component(name="lwip_echo_server")
comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = platform.build()

status = comp.clean()

comp.build()

status = platform.build()

comp.build()

