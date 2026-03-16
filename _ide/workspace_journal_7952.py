# 2026-03-13T00:26:50.383283300
import vitis

client = vitis.create_client()
client.set_workspace(path="D:/vitis_projects")

comp = client.create_app_component(name="mlp_app",platform = "$COMPONENT_LOCATION/../mlp_platform/export/mlp_platform/mlp_platform.xpfm",domain = "standalone_ps7_cortexa9_0")

platform = client.get_component(name="mlp_platform")
domain = platform.get_domain(name="standalone_ps7_cortexa9_0")

status = domain.set_lib(lib_name="lwip220", path="D:\AMDDesignTools\2025.2\Vitis\data\embeddedsw\ThirdParty\sw_services\lwip220_v1_3")

status = platform.build()

status = platform.build()

status = platform.build()

comp = client.get_component(name="mlp_app")
comp.build()

status = platform.build()

comp.build()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = comp.clean()

status = platform.build()

comp.build()

status = domain.set_config(option = "lib", param = "lwip220_temac_phy_link_speed", value = "CONFIG_LINKSPEED100", lib_name="lwip220")

status = platform.build()

status = platform.build()

comp.build()

status = platform.build()

comp.build()

vitis.dispose()

vitis.dispose()

