# Python App

## Overview

This Python application is designed to interact with Azure services using secure authentication and environment-based configurations. It leverages the `DefaultAzureCredential` from the `azure.identity` package to seamlessly manage authentication across local development and production environments. Additionally, the project supports a containerized development environment using a DevContainer configuration, making it easier to onboard new contributors and maintain consistency across development setups.

## Features

- **Azure Authentication:** Uses `DefaultAzureCredential` to automatically select the appropriate authentication method based on the environment.
- **Environment Configuration:** Requires a `.env` file for storing sensitive credentials and configuration variables.
- **Containerized Development:** Includes a DevContainer configuration for a ready-to-use development environment in Visual Studio Code.
- **Modular Design:** Organized project structure for clarity and ease of maintenance.

## Prerequisites

- **Python:** Version 3.7 or later.
- **Azure Subscription:** Ensure you have valid Azure credentials.
- **Docker:** Required for using the DevContainer (optional but recommended).
- **VS Code:** With the [Remote - Containers extension](https://code.visualstudio.com/docs/remote/containers) if you plan to use the DevContainer.
- **Pip:** For managing Python packages.

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/your-repository.git
cd your-repository
```

### 2. Set Up a Virtual Environment and Install Dependencies

It is recommended to use a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Create a `.env` File

The application requires a `.env` file in the root directory to load sensitive credentials and other configuration variables. Create a file named `.env` and include the following environment variables:

```ini
# Azure Credentials (required for DefaultAzureCredential)
AZURE_CLIENT_ID=<your-azure-client-id>
AZURE_TENANT_ID=<your-azure-tenant-id>
AZURE_CLIENT_SECRET=<your-azure-client-secret>

# Additional configuration variables (if any)
# e.g., API_ENDPOINT=https://your-api-endpoint.com
```

**Note:** You can use the provided `.env.example` as a reference.

### 4. Running the Application

To run the application, execute the main module:

```bash
python app/main.py
```

Ensure that your `.env` file is correctly set up so that the application can load the necessary configuration variables.

## Azure Authentication with `DefaultAzureCredential`

The application uses the `DefaultAzureCredential` class from the `azure.identity` package. This class simplifies the process of authentication by automatically determining the best available credential based on the environment. During local development, it relies on the credentials provided in your `.env` file (or your local Azure CLI session), and in production, it can utilize managed identities or other secure methods.

Ensure your Azure credentials are valid and that you have the necessary permissions to access the Azure resources required by the application.

## Using the DevContainer

For an optimized development experience, the project includes a DevContainer configuration. This allows you to run the application within a Docker container that has all the required dependencies and configurations pre-installed.

### How to Use the DevContainer

1. **Install Docker:** Make sure Docker is installed and running on your machine.
2. **Install VS Code:** Install Visual Studio Code.
3. **Install Remote - Containers Extension:** In VS Code, install the Remote - Containers extension.
4. **Open the Project in a Container:**
   - Open the project folder in VS Code.
   - When prompted, select “Reopen in Container” to start the DevContainer.

The DevContainer configuration is located in the `.devcontainer` directory and includes all necessary settings for a consistent development environment.

## Project Structure

Below is an example of the project structure:

```plaintext
├── app/                    
│   ├── main.py             # Main entry point of the application
│   ├── config.py           # Handles configuration and .env loading
│   └── ...                 # Other modules and packages
├── .env.example            # Example file for environment variables
├── .devcontainer/          
│   ├── devcontainer.json   # VS Code DevContainer configuration
│   └── ...                 # Additional container setup files
├── requirements.txt        # List of Python dependencies
└── README.md               # This file
```

## Troubleshooting

### Azure Authentication Issues

- Verify that your `.env` file contains the correct values for `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_CLIENT_SECRET`.
- Ensure these credentials have the proper permissions to access the required Azure resources.

### DevContainer Issues

- Ensure Docker is installed and running.
- Confirm that the Remote - Containers extension is installed in VS Code.
- Check the logs within the DevContainer for any errors related to dependency installation or configuration.

## Contributing

Contributions are welcome! If you would like to contribute, please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Commit your changes and open a pull request.
4. Ensure your code adheres to the project's style and testing guidelines.

## License

This project is licensed under the MIT License. See the `LICENSE` file for more details.

