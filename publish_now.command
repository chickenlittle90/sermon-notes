#!/bin/zsh
# Double-click this file to publish the latest sermon from your Mac.
# It asks for your Anthropic API key privately (the typing stays hidden),
# generates the notes, and updates the site files. Then you push in GitHub Desktop.

cd "$(dirname "$0")" || exit 1
source venv/bin/activate

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Paste your Anthropic API key, then press Enter."
  echo "(Nothing will show as you paste - that's normal, it's kept hidden.)"
  read -s ANTHROPIC_API_KEY
  export ANTHROPIC_API_KEY
  echo ""
  echo "Thanks. Working on it..."
  echo ""
fi

python publish_latest.py

echo ""
echo "------------------------------------------------------------"
echo "If it says 'Published' above, now open GitHub Desktop and"
echo "click Push to origin to update the website."
echo "------------------------------------------------------------"
echo "Press Enter to close this window."
read
