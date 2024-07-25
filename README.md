# Verus Copilot for Visual Studio Code

*Still under development*

## Installation

* Install [rust](https://www.rust-lang.org/tools/install)
* Install 

TODO

## Configuration

TODO

## Usage

TODO

## Responsible AI FAQ

- **What is Verus Copilot?**
    - Verus Copilot is a VS Code extension that can automatically generate some of the Verus proof annotations with user's code and help developers prove the correctness of Rust programs.
- **What can Verus Copilot do?**
    - Verus Copilot provide code action suggestions (lightbulb icon) to vscode editor while user writing verus / rust code. 
    - When code action triggered, the extension will interact with user-provided OpenAI endpoints and verus binary to automatically generate or refine verus proof annotations.
- **What is Verus Copilot's intended use?**
    - It aims to automatically generate correctness proof for any programs written in Rust which will improve the correctness and security of the code.
- **How was Verus Copilot evaluated? What metrics are used to measure performance?**
    - Verus Copilot is evaluated by human on the quality of proof annotations and whether it saves time for developers. An internal manual created benchmark is also used to provide a reference result of the pipeline.
    - The evaluation metrics include the correctness of the proof annotations, the time delay in providing code suggestions, and the time saved by developers.
- **What are the limitations of Verus Copilot? How can users minimize the impact of Verus Copilot's limitations when using the system?**
    - **Code suggested by Verus Copilot may not always be correct.** Users should be careful and choose if the changes should be applied. If the extension detect a potential wrong or low quality result, it will alert user by prompting a warning message.
    - Verus Copilot is limited by the quality of provided OpenAI model. Users are encouraged to supply endpoint with high-quality OpenAI model.
    - Verus Copilot is also limited by the complexity of the code. Currently it only supports single Rust file without file-level dependencies. Users can minimize the impact of these limitations by providing simple and self-contained code.
- **What operational factors and settings allow for effective and responsible use of Verus Copilot?**
    - Users need to provide their own OpenAI endpoints and verus binary via vscode settings
        - The performance and accuracy of suggestions may be influcened by the model behind the provided endpoint.
    - Temperature of OpenAI model
        - The temperature affects the computation of token probabilities when generating output through the large language model.
        - Higher temperature can result in more creative results but also increase the risk of "hallucination" which often leads to wrong results.
    - Maximum number retries of Verus Copilot
        - The setting determines how many times the extension will communicate with the OpenAI endpoints to refine the results. More retries can lead to more responses, potentially improving the quality of final result.

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft 
trademarks or logos is subject to and must follow 
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
