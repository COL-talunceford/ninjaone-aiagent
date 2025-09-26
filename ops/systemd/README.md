# systemd service

## Install
```bash
sudo cp ops/systemd/ninja-agent.service /etc/systemd/system/ninja-agent.service
sudo systemctl daemon-reload
sudo systemctl enable ninja-agent
sudo systemctl start ninja-agent
