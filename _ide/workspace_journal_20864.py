# 2026-03-17T03:02:53.293409100
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.get_component(name="mlp_platform")
status = platform.build()

comp = client.get_component(name="lwip_echo_server")
comp.build()

vitis.dispose()

vitis.dispose()

