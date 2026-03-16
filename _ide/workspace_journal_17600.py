# 2026-03-13T00:21:49.000428800
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

platform = client.create_platform_component(name = "mlp_platform",hw_design = "$COMPONENT_LOCATION/../mlp_system_wrapper.xsa",os = "standalone",cpu = "ps7_cortexa9_0",domain_name = "standalone_ps7_cortexa9_0",compiler = "gcc")

status = client.add_platform_repos(platform=["d:\vitis_projects"])

