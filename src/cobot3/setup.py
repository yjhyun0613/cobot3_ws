from setuptools import find_packages, setup

package_name = 'cobot3'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'control_tower = cobot3.control_tower_node:main',
            'sim_sync_node = cobot3.sim_sync_node:main',
            'mock_sg2_out = cobot3.mock_sg2_out_node:main',
            'mock_amr = cobot3.mock_amr_node:main',
            'mock_sg2 = cobot3.mock_sg2_node:main',
        ],
    },
)
